from typing import Dict, List, Optional

from .analyzer import AnalysisResult
from .code_context import build_code_change_context
from .data_builder import ClassifiedCommit, classify_commits
from .project_context import build_project_context_section
from .rendering import bullet_list, risk_list


def filter_detail_data(
    raw_data: Dict,
    author: Optional[str] = None,
    path_filters: Optional[List[str]] = None,
    commit_filters: Optional[List[str]] = None,
) -> Dict:
    path_filters = [item.lower().replace("\\", "/") for item in (path_filters or []) if item]
    commit_filters = [item.lower() for item in (commit_filters or []) if item]
    details_by_sha = {_sha(item): item for item in raw_data.get("commit_details", []) if _sha(item)}

    filtered_commits = []
    filtered_details = []
    for commit in raw_data.get("commits", []):
        sha = _sha(commit)
        detail = details_by_sha.get(sha)
        if commit_filters and not any(sha.startswith(value) for value in commit_filters):
            continue
        if author and author.lower() not in _commit_actor_text(commit).lower():
            continue
        if path_filters and not _detail_matches_paths(detail, path_filters):
            continue
        filtered_commits.append(commit)
        if detail:
            filtered_details.append(detail)

    return {
        "commits": filtered_commits,
        "commit_details": filtered_details,
        "issues": raw_data.get("issues", []),
        "pull_requests": raw_data.get("pull_requests", []),
        "branches": raw_data.get("branches", []),
        "project_context": raw_data.get("project_context", []),
    }


def build_detail_worklog_context(raw_data: Dict, classified: List[ClassifiedCommit], args) -> str:
    lines = [
        "# Detailed work log context",
        "",
        "## Scope",
        "- Repository: {0}".format(getattr(args, "repo_url", "")),
        "- Branch: {0}".format(getattr(args, "branch", "main")),
        "- Range: last {0} days".format(getattr(args, "days", 7)),
        "- Author filter: {0}".format(getattr(args, "author", None) or "-"),
        "- Path filters: {0}".format(", ".join(getattr(args, "path_filter", []) or []) or "-"),
        "- Commit filters: {0}".format(", ".join(getattr(args, "commit", []) or []) or "-"),
        "",
        "## Project context documents",
        build_project_context_section(raw_data.get("project_context", [])),
        "",
        "## Commits",
        "\n".join(_format_commit(item) for item in classified) or "- None",
        "",
        "## Code evidence",
        build_code_change_context(
            raw_data.get("commit_details", []),
            max_files=getattr(args, "max_files_per_commit", 20),
            max_patch_chars=getattr(args, "max_patch_chars", 5000),
        ),
        "",
        "## File content snapshots",
        build_file_snapshot_context(
            raw_data.get("file_snapshots", []),
            max_chars=getattr(args, "max_file_content_chars", 2500),
        ),
        "",
        "Please generate a detailed work log. Cover completed work, changed files, implementation evidence, and follow-up items.",
    ]
    return "\n".join(lines)


def build_detail_raw_report(raw_data: Dict, classified: List[ClassifiedCommit], args) -> str:
    return "\n".join(
        [
            "# 详细工作日志",
            "",
            "## 筛选范围",
            "",
            "- 仓库: {0}".format(getattr(args, "repo_url", "")),
            "- 作者: {0}".format(getattr(args, "author", None) or "-"),
            "- 路径: {0}".format(", ".join(getattr(args, "path_filter", []) or []) or "-"),
            "- Commit: {0}".format(", ".join(getattr(args, "commit", []) or []) or "-"),
            "",
            "## 项目上下文",
            "",
            build_project_context_section(raw_data.get("project_context", [])),
            "",
            "## 完成工作",
            "",
            bullet_list([item.full_message for item in classified]),
            "",
            "## 代码证据",
            "",
            build_code_change_context(
                raw_data.get("commit_details", []),
                max_files=getattr(args, "max_files_per_commit", 20),
                max_patch_chars=getattr(args, "max_patch_chars", 5000),
            ),
            "",
            "## 文件内容快照",
            "",
            build_file_snapshot_context(
                raw_data.get("file_snapshots", []),
                max_chars=getattr(args, "max_file_content_chars", 2500),
            ),
        ]
    ).strip() + "\n"


def format_detail_ai_report(analysis: AnalysisResult, raw_data: Dict, classified: List[ClassifiedCommit], args) -> str:
    return "\n".join(
        [
            "# 详细工作日志",
            "",
            analysis.summary.strip(),
            "",
            "## 项目上下文",
            "",
            build_project_context_section(raw_data.get("project_context", [])),
            "",
            "## 完成工作",
            "",
            bullet_list(analysis.facts or [item.full_message for item in classified]),
            "",
            "## 实现判断",
            "",
            bullet_list(analysis.inferences),
            "",
            "## 风险",
            "",
            risk_list(analysis.risks),
            "",
            "## 后续事项",
            "",
            bullet_list(analysis.suggestions),
            "",
            "## 代码证据",
            "",
            build_code_change_context(
                raw_data.get("commit_details", []),
                max_files=getattr(args, "max_files_per_commit", 20),
                max_patch_chars=getattr(args, "max_patch_chars", 5000),
            ),
            "",
            "## 文件内容快照",
            "",
            build_file_snapshot_context(
                raw_data.get("file_snapshots", []),
                max_chars=getattr(args, "max_file_content_chars", 2500),
            ),
        ]
    ).strip() + "\n"


def classify_detail_commits(raw_data: Dict) -> List[ClassifiedCommit]:
    return classify_commits(raw_data.get("commits", []))


def collect_file_snapshot_targets(raw_data: Dict, max_files: int = 8) -> List[Dict]:
    targets: List[Dict] = []
    seen = set()
    for detail in raw_data.get("commit_details", []):
        ref = _sha_full(detail)
        for file_item in detail.get("files", []) or []:
            path = _filename(file_item)
            if not path:
                continue
            key = (ref, path)
            if key in seen:
                continue
            seen.add(key)
            targets.append({"ref": ref, "path": path})
            if len(targets) >= max_files:
                return targets
    return targets


def build_file_snapshot_context(snapshots: List[Dict], max_chars: int = 2500) -> str:
    if not snapshots:
        return "- No file content snapshots fetched."
    sections: List[str] = []
    for item in snapshots:
        header = "### {0} @ {1}".format(item.get("path", "unknown"), str(item.get("ref", ""))[:8] or "-")
        if item.get("error"):
            sections.extend([header, "- Fetch failed: {0}".format(item["error"]), ""])
            continue
        content = (item.get("content") or "").strip()
        if not content:
            sections.extend([header, "- Empty or binary file.", ""])
            continue
        sections.extend(
            [
                header,
                "```",
                _truncate(content, max_chars),
                "```",
                "",
            ]
        )
    return "\n".join(sections).strip()


def _format_commit(commit: ClassifiedCommit) -> str:
    return "- {0} {1} ({2}, {3})".format(
        commit.sha,
        commit.full_message,
        commit.author or "unknown",
        commit.date[:10] if commit.date else "unknown-date",
    )


def _sha(item: Dict) -> str:
    return str(item.get("sha") or item.get("id") or "")[:8].lower()


def _sha_full(item: Dict) -> str:
    return str(item.get("sha") or item.get("id") or "")


def _filename(file_item: Dict) -> str:
    return (
        file_item.get("filename")
        or file_item.get("name")
        or file_item.get("path")
        or ""
    )


def _commit_actor_text(commit: Dict) -> str:
    parts = []
    api_author = commit.get("author")
    if isinstance(api_author, dict):
        parts.extend(str(api_author.get(key, "")) for key in ("login", "username", "full_name", "email"))
    commit_author = (commit.get("commit", {}) or {}).get("author", {}) or {}
    parts.extend(str(commit_author.get(key, "")) for key in ("name", "email"))
    return " ".join(parts)


def _detail_matches_paths(detail: Optional[Dict], path_filters: List[str]) -> bool:
    if not detail:
        return False
    for file_item in detail.get("files", []) or []:
        filename = (
            file_item.get("filename")
            or file_item.get("name")
            or file_item.get("path")
            or ""
        ).lower().replace("\\", "/")
        if any(path_filter in filename for path_filter in path_filters):
            return True
    return False


def _truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n... truncated"
