"""代码变更上下文模块 —— 从 commit_details 中提取文件变更统计和 patch 摘录，供 AI 分析使用。"""

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Dict, Iterable, List


# 源码文件扩展名集合，用于文件类型分类
SOURCE_EXTENSIONS = {
    ".c", ".cc", ".cpp", ".cs", ".go", ".java", ".js", ".jsx",
    ".kt", ".m", ".php", ".py", ".rs", ".swift", ".ts", ".tsx", ".vue",
}
# 测试目录名称提示词
TEST_HINTS = ("test", "tests", "__tests__", "spec")
# 文档文件扩展名集合
DOC_EXTENSIONS = {".md", ".rst", ".txt", ".adoc"}
# 配置文件名称集合（小写）
CONFIG_NAMES = {
    ".env", ".gitignore", "dockerfile", "makefile",
    "package.json", "pyproject.toml", "requirements.txt",
    "pom.xml", "build.gradle",
}


@dataclass
class CodeChangeSummary:
    """代码变更统计摘要，聚合多个 commit 的文件变更信息。"""

    commit_count: int = 0
    file_count: int = 0
    additions: int = 0
    deletions: int = 0
    by_category: Dict[str, int] = field(default_factory=dict)  # 按文件类型分类的变更文件数
    touched_files: List[str] = field(default_factory=list)      # 变更文件路径样例列表
    patch_excerpt: str = ""                                      # 拼接的 patch 摘录文本


def normalize_commit_details(commit_details: Iterable[Dict]) -> List[Dict]:
    """过滤并返回有效的 commit detail 字典列表。"""
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
    """聚合多个 commit 的代码变更统计，包括文件数、增删行数、类型分布和 patch 摘录。"""
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
            # 当 commit 级别没有 stats 时，从文件级别累加增删行数
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
    """构建供 AI 分析的代码变更上下文文本，包含统计摘要和 patch 摘录。"""
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
    """将文件路径分类为 source / test / docs / config / other 之一。"""
    if not path:
        return "other"
    normalized = path.replace("\\", "/").lower()
    parts = [part for part in normalized.split("/") if part]
    name = parts[-1] if parts else normalized
    suffix = PurePosixPath(normalized).suffix
    # 测试文件：路径包含测试目录名或文件名以 test_ 开头
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
    """从 commit detail 中提取文件变更列表，兼容大小写字段名。"""
    files = detail.get("files") or detail.get("Files") or []
    if isinstance(files, list):
        return [item for item in files if isinstance(item, dict)]
    return []


def _filename(file_item: Dict) -> str:
    """从文件变更字典中提取文件路径，兼容多种字段名。"""
    return (
        file_item.get("filename")
        or file_item.get("name")
        or file_item.get("path")
        or file_item.get("old_filename")
        or ""
    )


def _commit_patch_excerpt(detail: Dict, max_chars: int) -> str:
    """从单个 commit detail 中提取 patch 摘录，格式为 ### sha filename + diff 内容。"""
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
    """将类型计数字典格式化为 "key:count, ..." 字符串。"""
    if not counts:
        return "-"
    return ", ".join("{0}:{1}".format(key, counts[key]) for key in sorted(counts))


def _int_value(value) -> int:
    """安全地将任意值转换为整数，转换失败时返回 0。"""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _truncate(text: str, max_chars: int) -> str:
    """截断文本到指定字符数，超出时追加截断提示。"""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n... truncated"
