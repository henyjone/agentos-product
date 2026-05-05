"""数据构建模块 —— 对 commit 列表进行分类统计、风险识别，并构建供 AI 分析的上下文文本。"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .code_context import build_code_change_context
from .project_context import build_project_context_section


# 支持的 Conventional Commit 类型
COMMIT_TYPES = ("feat", "fix", "refactor", "docs", "test", "chore", "perf", "revert")
# 匹配 Conventional Commit 格式的正则：type(scope): description
COMMIT_PATTERN = re.compile(
    r"^(feat|fix|refactor|docs|test|chore|perf|revert)(\([^)]+\))?:\s*(.+)$"
)


@dataclass(frozen=True)
class ClassifiedCommit:
    """经过分类的提交记录，包含解析后的 type、scope 和描述。"""

    sha: str
    full_message: str   # 提交信息第一行（原始）
    type: str           # 提交类型，不符合规范时为 "uncategorized"
    scope: Optional[str]
    description: str    # 去除 type(scope): 前缀后的描述文本
    author: str
    date: str


@dataclass(frozen=True)
class CommitStats:
    """提交统计数据，包含总数、按类型分布和格式规范率。"""

    total: int
    by_type: Dict[str, int]
    uncategorized: int
    format_compliance_rate: float  # 符合 Conventional Commit 格式的比例


@dataclass(frozen=True)
class RiskSignal:
    """内置风险信号，由规则引擎识别。"""

    signal: str   # 风险名称
    basis: str    # 风险依据（具体数据）
    severity: str # 严重程度：high / medium / low


def classify_commits(raw_commits: List[Dict]) -> List[ClassifiedCommit]:
    """将 Gitea API 返回的原始 commit 列表解析为 ClassifiedCommit 列表。

    不符合 Conventional Commit 格式的提交归类为 uncategorized。
    """
    classified: List[ClassifiedCommit] = []
    for item in raw_commits:
        commit = item.get("commit", {}) or {}
        message = commit.get("message", item.get("message", "")) or ""
        first_line = message.splitlines()[0].strip() if message.strip() else ""
        match = COMMIT_PATTERN.match(first_line)
        author = commit.get("author", {}) or {}
        if match:
            scope = match.group(2).strip("()") if match.group(2) else None
            classified.append(
                ClassifiedCommit(
                    sha=(item.get("sha") or item.get("id") or "")[:8],
                    full_message=first_line,
                    type=match.group(1),
                    scope=scope,
                    description=match.group(3).strip(),
                    author=author.get("name", item.get("author", "")) or "",
                    date=author.get("date", item.get("date", "")) or "",
                )
            )
        else:
            classified.append(
                ClassifiedCommit(
                    sha=(item.get("sha") or item.get("id") or "")[:8],
                    full_message=first_line,
                    type="uncategorized",
                    scope=None,
                    description=first_line[:100],
                    author=author.get("name", item.get("author", "")) or "",
                    date=author.get("date", item.get("date", "")) or "",
                )
            )
    return classified


def compute_stats(classified: List[ClassifiedCommit]) -> CommitStats:
    """计算提交统计数据，包括按类型分布和格式规范率。"""
    by_type = {commit_type: 0 for commit_type in COMMIT_TYPES}
    uncategorized = 0
    for commit in classified:
        if commit.type == "uncategorized":
            uncategorized += 1
        else:
            by_type[commit.type] = by_type.get(commit.type, 0) + 1
    total = len(classified)
    compliance = (total - uncategorized) / total if total else 0.0
    return CommitStats(
        total=total,
        by_type={key: value for key, value in by_type.items() if value},
        uncategorized=uncategorized,
        format_compliance_rate=compliance,
    )


def identify_builtin_risks(
    classified: List[ClassifiedCommit],
    raw_data: Dict,
    days: int,
    now: Optional[datetime] = None,
) -> List[RiskSignal]:
    """基于规则识别内置风险信号，包括无活动、Issue 积压、分支过多、格式规范率低等。"""
    now = now or datetime.now(timezone.utc)
    stats = compute_stats(classified)
    risks: List[RiskSignal] = []
    issues = raw_data.get("issues", [])
    prs = raw_data.get("pull_requests", [])
    branches = raw_data.get("branches", [])

    if stats.total == 0 and days >= 7:
        risks.append(RiskSignal("无近期活动", "最近 {0} 天无 commit".format(days), "high"))
    if len(issues) > 20:
        risks.append(RiskSignal("开放 issue 较多", "当前开放 issue 数为 {0}".format(len(issues)), "medium"))
    if len(branches) > 10:
        risks.append(RiskSignal("并行分支较多", "当前分支数为 {0}".format(len(branches)), "low"))
    if stats.total and stats.format_compliance_rate < 0.5:
        risks.append(
            RiskSignal(
                "commit 格式规范率低",
                "规范率为 {0:.1%}".format(stats.format_compliance_rate),
                "low",
            )
        )

    # 检查长期未关闭的 Issue（超过 30 天）
    for issue in issues:
        created_at = _parse_datetime(issue.get("created_at"))
        if created_at and (now - created_at).days > 30:
            risks.append(
                RiskSignal(
                    "长期未关闭 issue",
                    "#{0} 已开放 {1} 天".format(issue.get("number", "?"), (now - created_at).days),
                    "medium",
                )
            )

    # 检查长期未合并的 PR（超过 7 天）
    for pr in prs:
        created_at = _parse_datetime(pr.get("created_at"))
        if created_at and (now - created_at).days > 7:
            risks.append(
                RiskSignal(
                    "PR 长期未合并",
                    "#{0} 已开放 {1} 天".format(pr.get("number", "?"), (now - created_at).days),
                    "medium",
                )
            )
    return risks


def build_analysis_context(classified: List[ClassifiedCommit], raw_data: Dict, args) -> str:
    """构建供 AI 分析的完整上下文文本，包含项目信息、提交统计、Issue/PR/分支列表和代码变更证据。"""
    stats = compute_stats(classified)
    risks = identify_builtin_risks(classified, raw_data, getattr(args, "days", 7))
    max_commits = getattr(args, "max_commits", 50)
    repo_url = getattr(args, "repo_url", "")
    branch = getattr(args, "branch", "main")
    days = getattr(args, "days", 7)

    sections = [
        "## 项目信息",
        "- 仓库: {0}".format(repo_url),
        "- 分支: {0}".format(branch),
        "- 分析范围: 最近 {0} 天".format(days),
        "",
        "## Project Context Documents",
        build_project_context_section(raw_data.get("project_context", [])),
        "",
        "## Commit 统计",
        "- 总计: {0} 条".format(stats.total),
        "- 格式规范率: {0:.1%}".format(stats.format_compliance_rate),
        _type_table(stats),
        "",
        "## Commit 列表（最近 {0} 条）".format(min(max_commits, len(classified))),
        "\n".join(_format_commit(commit) for commit in classified[:max_commits]) or "- 无",
        "",
        "## 开放 Issue（{0} 个）".format(len(raw_data.get("issues", []))),
        "\n".join(_format_issue(item) for item in raw_data.get("issues", [])[:20]) or "- 无",
        "",
        "## 开放 PR（{0} 个）".format(len(raw_data.get("pull_requests", []))),
        "\n".join(_format_pr(item) for item in raw_data.get("pull_requests", [])[:20]) or "- 无",
        "",
        "## 活跃分支（{0} 个）".format(len(raw_data.get("branches", []))),
        "\n".join(_format_branch(item) for item in raw_data.get("branches", [])[:15]) or "- 无",
        "",
        "## Code Change Evidence",
        build_code_change_context(
            raw_data.get("commit_details", []),
            max_files=getattr(args, "max_files_per_commit", 12),
            max_patch_chars=getattr(args, "max_patch_chars", 1200),
        ),
        "",
        "## 内置风险信号",
        "\n".join("- [{0}] {1}: {2}".format(r.severity, r.signal, r.basis) for r in risks) or "- 无",
        "",
        "请基于以上数据生成项目状态摘要。事实必须来自数据，代码判断必须引用 Code Change Evidence。",
    ]
    return _truncate("\n".join(sections), 24000)


def _type_table(stats: CommitStats) -> str:
    """生成 commit 类型分布的 Markdown 表格。"""
    lines = ["| Type | 数量 |", "|---|---:|"]
    for commit_type in COMMIT_TYPES:
        if stats.by_type.get(commit_type):
            lines.append("| {0} | {1} |".format(commit_type, stats.by_type[commit_type]))
    if stats.uncategorized:
        lines.append("| uncategorized | {0} |".format(stats.uncategorized))
    return "\n".join(lines)


def _format_commit(commit: ClassifiedCommit) -> str:
    return "- {0} {1} ({2}, {3})".format(
        commit.sha or "unknown",
        commit.full_message or commit.description or "(empty)",
        commit.author or "unknown",
        commit.date[:10] if commit.date else "unknown-date",
    )


def _format_issue(item: Dict) -> str:
    return "- #{0} {1} ({2})".format(
        item.get("number", "?"),
        item.get("title", ""),
        item.get("created_at", "")[:10],
    )


def _format_pr(item: Dict) -> str:
    user = item.get("user", {}) or {}
    return "- #{0} {1} ({2}, {3})".format(
        item.get("number", "?"),
        item.get("title", ""),
        user.get("login", "unknown"),
        item.get("created_at", "")[:10],
    )


def _format_branch(item: Dict) -> str:
    commit = item.get("commit", {}) or {}
    return "- {0} ({1})".format(item.get("name", "unknown"), commit.get("id", "")[:8])


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    """解析 ISO 8601 时间字符串，自动处理 Z 后缀和无时区信息的情况。"""
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _truncate(text: str, max_chars: int) -> str:
    """截断文本到指定字符数，超出时追加截断提示。"""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... (context truncated)"
