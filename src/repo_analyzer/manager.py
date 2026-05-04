from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Set

from .analyzer import AnalysisResult
from .code_context import build_code_change_context, summarize_code_changes
from .data_builder import ClassifiedCommit, compute_stats, identify_builtin_risks
from .gitea_client import RepoRef


@dataclass
class RepositoryActivity:
    repo: RepoRef
    branch: str
    raw_data: Dict[str, List[Dict]]
    classified: List[ClassifiedCommit]
    errors: List[str] = field(default_factory=list)


@dataclass
class EmployeeSummary:
    identity: str
    commits: int = 0
    open_issues: int = 0
    open_prs: int = 0
    commit_types: Dict[str, int] = field(default_factory=dict)
    repos: Set[str] = field(default_factory=set)
    samples: List[str] = field(default_factory=list)
    latest_activity: str = ""


def build_employee_summaries(activities: Iterable[RepositoryActivity]) -> List[EmployeeSummary]:
    summaries: Dict[str, EmployeeSummary] = {}
    for activity in activities:
        repo_name = _repo_name(activity.repo)
        raw_commits = activity.raw_data.get("commits", [])
        for raw, commit in zip(raw_commits, activity.classified):
            actor = _commit_actor(raw, commit)
            summary = _summary_for(summaries, actor)
            summary.commits += 1
            summary.commit_types[commit.type] = summary.commit_types.get(commit.type, 0) + 1
            summary.repos.add(repo_name)
            _update_latest(summary, commit.date)
            if len(summary.samples) < 5:
                summary.samples.append(
                    "{0}: {1} {2}".format(repo_name, commit.sha or "unknown", commit.full_message)
                )

        for issue in activity.raw_data.get("issues", []):
            actor = _user_actor(issue.get("user", {}) or {})
            summary = _summary_for(summaries, actor)
            summary.open_issues += 1
            summary.repos.add(repo_name)
            _update_latest(summary, issue.get("created_at", ""))

        for pr in activity.raw_data.get("pull_requests", []):
            actor = _user_actor(pr.get("user", {}) or {})
            summary = _summary_for(summaries, actor)
            summary.open_prs += 1
            summary.repos.add(repo_name)
            _update_latest(summary, pr.get("created_at", ""))

    return sorted(
        summaries.values(),
        key=lambda item: (
            item.commits + item.open_issues + item.open_prs,
            item.commits,
            item.open_prs,
            item.identity.lower(),
        ),
        reverse=True,
    )


def build_manager_overview(activities: List[RepositoryActivity]) -> Dict[str, int]:
    return {
        "repo_count": len(activities),
        "repos_with_commits": sum(1 for item in activities if item.classified),
        "commit_count": sum(len(item.classified) for item in activities),
        "open_issue_count": sum(len(item.raw_data.get("issues", [])) for item in activities),
        "open_pr_count": sum(len(item.raw_data.get("pull_requests", [])) for item in activities),
        "error_count": sum(len(item.errors) for item in activities),
        "code_commit_count": sum(len(item.raw_data.get("commit_details", [])) for item in activities),
    }


def build_manager_analysis_context(
    activities: List[RepositoryActivity],
    employees: List[EmployeeSummary],
    args,
    history_context: str = "",
) -> str:
    overview = build_manager_overview(activities)
    lines = [
        "# Gitea manager daily context",
        "",
        "## Scope",
        "- Base URL: {0}".format(getattr(args, "base_url", "")),
        "- Range: last {0} days".format(getattr(args, "days", 7)),
        "- Repositories scanned: {0}".format(overview["repo_count"]),
        "- Repositories with commits: {0}".format(overview["repos_with_commits"]),
        "- Commits: {0}".format(overview["commit_count"]),
        "- Commits with code details: {0}".format(overview["code_commit_count"]),
        "- Open issues: {0}".format(overview["open_issue_count"]),
        "- Open pull requests: {0}".format(overview["open_pr_count"]),
        "",
        "## Employee summary",
        _employee_table(employees[:50]),
        "",
        "## Repository summary",
        _repo_table(activities[:100], getattr(args, "days", 7)),
        "",
        "## Code change evidence",
        _code_change_sections(activities[:50], args),
        "",
        "## Previous report history",
        history_context or "- No previous summary snapshots loaded.",
        "",
        "## Data fetch warnings",
        _error_lines(activities) or "- None",
        "",
        "Please generate a manager-facing daily report. Separate facts from AI judgment. "
        "Use code diff evidence when judging work content or code risk.",
    ]
    return _truncate("\n".join(lines), 32000)


def build_manager_raw_report(
    activities: List[RepositoryActivity],
    employees: List[EmployeeSummary],
    args,
    history_report: str = "",
) -> str:
    overview = build_manager_overview(activities)
    lines = [
        "# Gitea 管理者日报",
        "",
        "> AI 分析未启用或不可用，以下为按仓库、员工和代码变更聚合的原始数据摘要。",
        "",
        "## 总览",
        "",
        "- Gitea: {0}".format(getattr(args, "base_url", "")),
        "- 分析范围: 最近 {0} 天".format(getattr(args, "days", 7)),
        "- 扫描仓库: {0}".format(overview["repo_count"]),
        "- 有提交的仓库: {0}".format(overview["repos_with_commits"]),
        "- Commit 总数: {0}".format(overview["commit_count"]),
        "- 已读取代码变更的 Commit: {0}".format(overview["code_commit_count"]),
        "- 开放 Issue: {0}".format(overview["open_issue_count"]),
        "- 开放 PR: {0}".format(overview["open_pr_count"]),
        "- 拉取警告: {0}".format(overview["error_count"]),
        "",
        "## 按员工汇总",
        "",
        _employee_table(employees),
        "",
        "## 按仓库汇总",
        "",
        _repo_table(activities, getattr(args, "days", 7)),
        "",
        "## 代码变更摘要",
        "",
        _code_report_sections(activities, args),
    ]
    if history_report:
        lines.extend(["", "## 历史参考", "", history_report])
    errors = _error_lines(activities)
    if errors:
        lines.extend(["", "## 数据拉取警告", "", errors])
    return "\n".join(lines).strip() + "\n"


def format_manager_ai_report(
    analysis: AnalysisResult,
    activities: List[RepositoryActivity],
    employees: List[EmployeeSummary],
    args,
    history_report: str = "",
) -> str:
    overview = build_manager_overview(activities)
    lines = [
        "# Gitea 管理者日报",
        "",
        analysis.summary.strip(),
        "",
        "## 数据总览",
        "",
        "- Gitea: {0}".format(getattr(args, "base_url", "")),
        "- 分析范围: 最近 {0} 天".format(getattr(args, "days", 7)),
        "- 扫描仓库: {0}".format(overview["repo_count"]),
        "- Commit 总数: {0}".format(overview["commit_count"]),
        "- 已读取代码变更的 Commit: {0}".format(overview["code_commit_count"]),
        "- 开放 Issue: {0}".format(overview["open_issue_count"]),
        "- 开放 PR: {0}".format(overview["open_pr_count"]),
        "",
        "## 事实",
        "",
        _bullet_list(analysis.facts),
        "",
        "## 推断",
        "",
        _bullet_list(analysis.inferences),
        "",
        "## 风险",
        "",
        _risk_list(analysis.risks),
        "",
        "## 建议",
        "",
        _bullet_list(analysis.suggestions),
        "",
        "## 按员工汇总",
        "",
        _employee_table(employees),
        "",
        "## 按仓库汇总",
        "",
        _repo_table(activities, getattr(args, "days", 7)),
        "",
        "## 代码变更摘要",
        "",
        _code_report_sections(activities, args),
    ]
    if history_report:
        lines.extend(["", "## 历史参考", "", history_report])
    errors = _error_lines(activities)
    if errors:
        lines.extend(["", "## 数据拉取警告", "", errors])
    return "\n".join(lines).strip() + "\n"


def _summary_for(summaries: Dict[str, EmployeeSummary], actor: str) -> EmployeeSummary:
    key = actor or "unknown"
    if key not in summaries:
        summaries[key] = EmployeeSummary(identity=key)
    return summaries[key]


def _commit_actor(raw: Dict, commit: ClassifiedCommit) -> str:
    api_author = raw.get("author")
    if isinstance(api_author, dict):
        actor = _user_actor(api_author)
        if actor != "unknown":
            return actor
    commit_author = (raw.get("commit", {}) or {}).get("author", {}) or {}
    return (
        commit_author.get("email")
        or commit_author.get("name")
        or commit.author
        or "unknown"
    )


def _user_actor(user: Dict) -> str:
    return user.get("login") or user.get("username") or user.get("full_name") or "unknown"


def _update_latest(summary: EmployeeSummary, value: str) -> None:
    if value and value > summary.latest_activity:
        summary.latest_activity = value


def _repo_name(repo: RepoRef) -> str:
    return repo.full_name or "{0}/{1}".format(repo.owner, repo.repo)


def _employee_table(employees: List[EmployeeSummary]) -> str:
    if not employees:
        return "- 暂无员工活动数据"
    lines = [
        "| 员工 | Commit | 开放 Issue | 开放 PR | 涉及仓库 | Commit 类型 | 最近活动 |",
        "|---|---:|---:|---:|---|---|---|",
    ]
    for item in employees:
        lines.append(
            "| {0} | {1} | {2} | {3} | {4} | {5} | {6} |".format(
                _escape_cell(item.identity),
                item.commits,
                item.open_issues,
                item.open_prs,
                _escape_cell(", ".join(sorted(item.repos)) or "-"),
                _escape_cell(_format_types(item.commit_types)),
                item.latest_activity[:10] if item.latest_activity else "-",
            )
        )
    return "\n".join(lines)


def _repo_table(activities: List[RepositoryActivity], days: int) -> str:
    if not activities:
        return "- 暂无仓库数据"
    lines = [
        "| 仓库 | 分支 | Commit | 规范率 | Code files | + / - | 开放 Issue | 开放 PR | 风险信号 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in activities:
        stats = compute_stats(item.classified)
        risks = identify_builtin_risks(item.classified, item.raw_data, days)
        code_summary = summarize_code_changes(item.raw_data.get("commit_details", []))
        lines.append(
            "| {0} | {1} | {2} | {3:.1%} | {4} | +{5}/-{6} | {7} | {8} | {9} |".format(
                _escape_cell(_repo_name(item.repo)),
                _escape_cell(item.branch),
                stats.total,
                stats.format_compliance_rate,
                code_summary.file_count,
                code_summary.additions,
                code_summary.deletions,
                len(item.raw_data.get("issues", [])),
                len(item.raw_data.get("pull_requests", [])),
                _escape_cell(", ".join(risk.signal for risk in risks[:3]) or "-"),
            )
        )
    return "\n".join(lines)


def _code_change_sections(activities: List[RepositoryActivity], args) -> str:
    sections: List[str] = []
    max_files = getattr(args, "max_files_per_commit", 12)
    max_patch_chars = getattr(args, "max_patch_chars", 1200)
    for item in activities:
        details = item.raw_data.get("commit_details", [])
        if not details:
            continue
        sections.extend(
            [
                "### {0}".format(_repo_name(item.repo)),
                build_code_change_context(
                    details,
                    max_files=max_files,
                    max_patch_chars=max_patch_chars,
                ),
                "",
            ]
        )
    return "\n".join(sections).strip() or "- No code diff details were fetched."


def _code_report_sections(activities: List[RepositoryActivity], args) -> str:
    sections: List[str] = []
    max_files = getattr(args, "max_files_per_commit", 12)
    for item in activities:
        details = item.raw_data.get("commit_details", [])
        if not details:
            continue
        summary = summarize_code_changes(details, max_files=max_files, max_patch_chars=0)
        sections.append(
            "- {0}: {1} commits, {2} files, +{3}/-{4}, categories {5}, files {6}".format(
                _repo_name(item.repo),
                summary.commit_count,
                summary.file_count,
                summary.additions,
                summary.deletions,
                _format_types(summary.by_category),
                ", ".join(summary.touched_files) or "-",
            )
        )
    return "\n".join(sections) if sections else "- No code diff details were fetched."


def _error_lines(activities: List[RepositoryActivity]) -> str:
    lines: List[str] = []
    for item in activities:
        for error in item.errors:
            lines.append("- {0}: {1}".format(_repo_name(item.repo), error))
    return "\n".join(lines)


def _format_types(types: Dict[str, int]) -> str:
    if not types:
        return "-"
    return ", ".join("{0}:{1}".format(key, value) for key, value in sorted(types.items()))


def _bullet_list(items: List[str]) -> str:
    if not items:
        return "- 无"
    return "\n".join("- {0}".format(item) for item in items)


def _risk_list(items: List[Dict]) -> str:
    if not items:
        return "- 无"
    return "\n".join(
        "- [{severity}] {signal}: {basis}".format(
            severity=item.get("severity", "medium"),
            signal=item.get("signal", ""),
            basis=item.get("basis", ""),
        )
        for item in items
    )


def _escape_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... (context truncated)"
