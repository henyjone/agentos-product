from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Dict, Iterable, List


SOURCE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".m",
    ".php",
    ".py",
    ".rs",
    ".swift",
    ".ts",
    ".tsx",
    ".vue",
}
TEST_HINTS = ("test", "tests", "__tests__", "spec")
DOC_EXTENSIONS = {".md", ".rst", ".txt", ".adoc"}
CONFIG_NAMES = {
    ".env",
    ".gitignore",
    "dockerfile",
    "makefile",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "pom.xml",
    "build.gradle",
}


@dataclass
class CodeChangeSummary:
    commit_count: int = 0
    file_count: int = 0
    additions: int = 0
    deletions: int = 0
    by_category: Dict[str, int] = field(default_factory=dict)
    touched_files: List[str] = field(default_factory=list)
    patch_excerpt: str = ""


def normalize_commit_details(commit_details: Iterable[Dict]) -> List[Dict]:
    normalized: List[Dict] = []
    for detail in commit_details:
        if isinstance(detail, dict):
            normalized.append(detail)
    return normalized


def summarize_code_changes(
    commit_details: Iterable[Dict],
    max_files: int = 20,
    max_patch_chars: int = 2500,
) -> CodeChangeSummary:
    details = normalize_commit_details(commit_details)
    summary = CodeChangeSummary(commit_count=len(details))
    patch_parts: List[str] = []

    for detail in details:
        files = _files(detail)
        summary.file_count += len(files)
        stats = detail.get("stats") or {}
        summary.additions += _int_value(stats.get("additions") or stats.get("total_additions"))
        summary.deletions += _int_value(stats.get("deletions") or stats.get("total_deletions"))

        for file_item in files:
            filename = _filename(file_item)
            category = classify_path(filename)
            summary.by_category[category] = summary.by_category.get(category, 0) + 1
            if filename and len(summary.touched_files) < max_files:
                summary.touched_files.append(filename)
            if not stats:
                summary.additions += _int_value(file_item.get("additions"))
                summary.deletions += _int_value(file_item.get("deletions"))

        if len("".join(patch_parts)) < max_patch_chars:
            excerpt = _commit_patch_excerpt(detail, max_patch_chars - len("".join(patch_parts)))
            if excerpt:
                patch_parts.append(excerpt)

    summary.patch_excerpt = "\n".join(patch_parts).strip()
    return summary


def build_code_change_context(
    commit_details: Iterable[Dict],
    max_files: int = 20,
    max_patch_chars: int = 2500,
) -> str:
    details = normalize_commit_details(commit_details)
    if not details:
        return "- No code diff details were fetched."

    summary = summarize_code_changes(details, max_files=max_files, max_patch_chars=max_patch_chars)
    lines = [
        "- Commits with code details: {0}".format(summary.commit_count),
        "- Changed files: {0}".format(summary.file_count),
        "- Additions/deletions: +{0}/-{1}".format(summary.additions, summary.deletions),
        "- Categories: {0}".format(_format_counts(summary.by_category)),
        "- Touched files: {0}".format(", ".join(summary.touched_files) or "-"),
    ]
    if summary.patch_excerpt:
        lines.extend(["", "Patch excerpts:", "```diff", summary.patch_excerpt, "```"])
    return "\n".join(lines)


def classify_path(path: str) -> str:
    if not path:
        return "other"
    normalized = path.replace("\\", "/").lower()
    parts = [part for part in normalized.split("/") if part]
    name = parts[-1] if parts else normalized
    suffix = PurePosixPath(normalized).suffix
    if any(part in TEST_HINTS or part.endswith("_test") for part in parts) or name.startswith("test_"):
        return "test"
    if suffix in DOC_EXTENSIONS or "docs" in parts or "doc" in parts:
        return "docs"
    if name in CONFIG_NAMES or suffix in {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".xml"}:
        return "config"
    if suffix in SOURCE_EXTENSIONS:
        return "source"
    return "other"


def _files(detail: Dict) -> List[Dict]:
    files = detail.get("files") or detail.get("Files") or []
    if isinstance(files, list):
        return [item for item in files if isinstance(item, dict)]
    return []


def _filename(file_item: Dict) -> str:
    return (
        file_item.get("filename")
        or file_item.get("name")
        or file_item.get("path")
        or file_item.get("old_filename")
        or ""
    )


def _commit_patch_excerpt(detail: Dict, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    commit_id = (detail.get("sha") or detail.get("id") or "")[:8]
    pieces: List[str] = []
    for file_item in _files(detail):
        patch = (file_item.get("patch") or file_item.get("diff") or "").strip()
        filename = _filename(file_item)
        if not patch:
            continue
        header = "### {0} {1}".format(commit_id or "commit", filename)
        pieces.append(header)
        pieces.append(_truncate(patch, max(200, max_chars // 2)))
        if len("\n".join(pieces)) >= max_chars:
            break
    return _truncate("\n".join(pieces), max_chars)


def _format_counts(counts: Dict[str, int]) -> str:
    if not counts:
        return "-"
    return ", ".join("{0}:{1}".format(key, counts[key]) for key in sorted(counts))


def _int_value(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n... truncated"
