import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Set

from .analyzer import AnalysisResult, WorkSummaryResult
from .code_context import build_code_change_context, summarize_code_changes
from .data_builder import ClassifiedCommit, compute_stats, identify_builtin_risks
from .gitea_client import RepoRef
from .project_context import build_project_context_section, summarize_project_context_documents
from .rendering import escape_cell, format_counts


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
    code_files: int = 0
    additions: int = 0
    deletions: int = 0
    code_categories: Dict[str, int] = field(default_factory=dict)
    latest_activity: str = ""


def build_employee_summaries(activities: Iterable[RepositoryActivity]) -> List[EmployeeSummary]:
    summaries: Dict[str, EmployeeSummary] = {}
    for activity in activities:
        repo_name = _repo_name(activity.repo)
        raw_commits = activity.raw_data.get("commits", [])
        details_by_sha = _details_by_sha(activity.raw_data.get("commit_details", []))
        for raw, commit in zip(raw_commits, activity.classified):
            actor = _commit_actor(raw, commit)
            summary = _summary_for(summaries, actor)
            summary.commits += 1
            summary.commit_types[commit.type] = summary.commit_types.get(commit.type, 0) + 1
            summary.repos.add(repo_name)
            _update_latest(summary, commit.date)
            detail = details_by_sha.get(_commit_sha(raw))
            if detail:
                _add_code_summary(summary, detail)
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
        "## Employee daily task brief",
        _employee_daily_tasks_section(employees),
        "",
        "## Project brief",
        _project_briefs_section(activities, getattr(args, "days", 7)),
        "",
        "## Employee summary",
        _employee_table(employees[:50]),
        "",
        "## Repository summary",
        _repo_table(activities[:100], getattr(args, "days", 7)),
        "",
        "## Project context documents",
        _project_context_sections(activities[:50]),
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
        "Use code diff evidence when judging work content or code risk. Keep the front summary concise.",
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
        "# Gitea 工作日报",
        "",
        "> 最近 {0} 天，扫描 {1} 个仓库，识别到 {2} 次提交。".format(
            getattr(args, "days", 7),
            overview["repo_count"],
            overview["commit_count"],
        ),
        "",
        "## 员工完成情况",
        "",
        _employee_work_digest_section(employees),
    ]
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
        "# Gitea 工作日报",
        "",
        "> 最近 {0} 天，扫描 {1} 个仓库，识别到 {2} 次提交。".format(
            getattr(args, "days", 7),
            overview["repo_count"],
            overview["commit_count"],
        ),
        "",
        "## 员工完成情况",
        "",
        _employee_work_digest_section(employees),
    ]
    errors = _error_lines(activities)
    if errors:
        lines.extend(["", "## 数据拉取警告", "", errors])
    return "\n".join(lines).strip() + "\n"


def build_manager_work_summary_context(
    activities: List[RepositoryActivity],
    employees: List[EmployeeSummary],
    args,
) -> str:
    overview = build_manager_overview(activities)
    lines = [
        "# Employee work summary context",
        "",
        "## Scope",
        "- Base URL: {0}".format(getattr(args, "base_url", "")),
        "- Range: last {0} days".format(getattr(args, "days", 7)),
        "- Repositories scanned: {0}".format(overview["repo_count"]),
        "- Commits: {0}".format(overview["commit_count"]),
        "- Commits with code details: {0}".format(overview["code_commit_count"]),
        "",
        "## Employee evidence",
    ]
    for employee in employees:
        lines.extend(
            [
                "### {0}".format(employee.identity),
                "- Commit count: {0}".format(employee.commits),
                "- Code files: {0}".format(employee.code_files),
                "- Additions/deletions: +{0}/-{1}".format(employee.additions, employee.deletions),
                "- Commit samples:",
                "\n".join("- {0}".format(item) for item in employee.samples[:8]) or "- None",
                "",
            ]
        )
    lines.extend(
        [
            "## Project context documents",
            _project_context_sections(activities[:50]),
            "",
            "Only return employees and completed work items. Do not include related project lists.",
        ]
    )
    return _truncate("\n".join(lines), 18000)


def format_manager_work_summary_report(
    summary: WorkSummaryResult,
    activities: List[RepositoryActivity],
    args,
) -> str:
    overview = build_manager_overview(activities)
    lines = [
        "# Gitea 工作日报",
        "",
        "> 最近 {0} 天，扫描 {1} 个仓库，识别到 {2} 次提交。".format(
            getattr(args, "days", 7),
            overview["repo_count"],
            overview["commit_count"],
        ),
        "",
        "## 员工完成情况",
        "",
    ]
    for employee in summary.employees:
        lines.extend(
            [
                "### {0}".format(employee.name),
                "- 完成工作:",
                _numbered_list(employee.work_items),
                "",
            ]
        )
    errors = _error_lines(activities)
    if errors:
        lines.extend(["## 数据拉取警告", "", errors, ""])
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
                escape_cell(item.identity),
                item.commits,
                item.open_issues,
                item.open_prs,
                escape_cell(", ".join(sorted(item.repos)) or "-"),
                escape_cell(format_counts(item.commit_types)),
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
                escape_cell(_repo_name(item.repo)),
                escape_cell(item.branch),
                stats.total,
                stats.format_compliance_rate,
                code_summary.file_count,
                code_summary.additions,
                code_summary.deletions,
                len(item.raw_data.get("issues", [])),
                len(item.raw_data.get("pull_requests", [])),
                escape_cell(", ".join(risk.signal for risk in risks[:3]) or "-"),
            )
        )
    return "\n".join(lines)


def _project_context_sections(activities: List[RepositoryActivity]) -> str:
    sections: List[str] = []
    for activity in activities:
        documents = activity.raw_data.get("project_context", [])
        if not documents:
            continue
        sections.extend(
            [
                "### {0}".format(_repo_name(activity.repo)),
                "- Documents: {0}".format(summarize_project_context_documents(documents)),
                build_project_context_section(documents, max_chars_per_file=1600),
                "",
            ]
        )
    return "\n".join(sections).strip() or "- No project context documents found."


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
                format_counts(summary.by_category),
                ", ".join(summary.touched_files) or "-",
            )
        )
    return "\n".join(sections) if sections else "- No code diff details were fetched."


def _employee_work_digest_section(employees: List[EmployeeSummary]) -> str:
    if not employees:
        return "- 暂无员工工作记录"
    lines: List[str] = []
    for employee in employees:
        lines.extend(
            [
                "### {0}".format(employee.identity),
                "- 完成工作:",
                _numbered_list(_employee_completed_work_items(employee)),
                "",
            ]
        )
    return "\n".join(lines).strip()


def _employee_daily_tasks_section(employees: List[EmployeeSummary]) -> str:
    if not employees:
        return "- 暂无员工活动数据"
    lines: List[str] = []
    for employee in employees:
        lines.extend(
            [
                "### {0}".format(employee.identity),
                "- 完成内容: {0}".format(_employee_completed_work(employee)),
                "- 参与项目: {0}".format(", ".join(sorted(employee.repos)) or "-"),
                "- 工作量线索: {0} 次 commit，涉及 {1} 个代码文件，增删行 +{2}/-{3}".format(
                    employee.commits,
                    employee.code_files,
                    employee.additions,
                    employee.deletions,
                ),
                "- 进度判断: {0}".format(_employee_progress(employee)),
                "",
            ]
        )
    return "\n".join(lines).strip()


def _project_briefs_section(activities: List[RepositoryActivity], days: int) -> str:
    if not activities:
        return "- 暂无仓库数据"
    lines: List[str] = []
    for activity in activities:
        stats = compute_stats(activity.classified)
        code_summary = summarize_code_changes(activity.raw_data.get("commit_details", []), max_patch_chars=0)
        risks = identify_builtin_risks(activity.classified, activity.raw_data, days)
        lines.extend(
            [
                "### {0}".format(_repo_name(activity.repo)),
                "- 进度: {0}".format(_project_progress(activity, code_summary)),
                "- 本次变更: {0} 次 commit，{1} 个变更文件，增删行 +{2}/-{3}".format(
                    stats.total,
                    code_summary.file_count,
                    code_summary.additions,
                    code_summary.deletions,
                ),
                "- 主要类型: {0}".format(format_counts(stats.by_type) if stats.by_type else "未识别规范类型"),
                "- 待补模块: {0}".format(_project_missing_modules(activity)),
                "- 潜在风险: {0}".format(_project_risks(risks)),
                "",
            ]
        )
    return "\n".join(lines).strip()


def _employee_completed_work(employee: EmployeeSummary) -> str:
    return "；".join(_employee_completed_work_items(employee))


def _employee_completed_work_items(employee: EmployeeSummary) -> List[str]:
    if not employee.samples:
        return ["未从最近提交中识别到明确完成项"]
    descriptions = []
    for sample in employee.samples[:3]:
        parts = sample.split(" ", 2)
        descriptions.append(_clean_work_description(parts[-1] if parts else sample))
    return descriptions


def _numbered_list(items: List[str]) -> str:
    if not items:
        return "1. 未识别到明确完成项"
    return "\n".join("{0}. {1}".format(index, item.rstrip("；;。")) for index, item in enumerate(items, start=1))


def _clean_work_description(value: str) -> str:
    text = value.strip()
    text = re.sub(r"^(feat|fix|refactor|docs|test|chore|perf|revert)(\([^)]+\))?:\s*", "", text)
    return text or value


def _employee_progress(employee: EmployeeSummary) -> str:
    if employee.commits == 0 and employee.open_prs == 0 and employee.open_issues == 0:
        return "本周期未识别到新增开发活动"
    if employee.open_prs:
        return "有开放 PR，说明相关工作可能处于评审或待合并阶段"
    if employee.commits:
        return "已有代码提交，功能处于推进或已落地阶段；具体完成度需结合项目验收确认"
    return "有 issue/PR 活动，但未识别到代码提交"


def _project_progress(activity: RepositoryActivity, code_summary) -> str:
    if activity.raw_data.get("pull_requests"):
        return "存在开放 PR，项目处于开发评审或待合并阶段"
    if activity.classified and code_summary.file_count:
        return "最近有代码变更，项目处于持续推进阶段"
    if activity.classified:
        return "最近有 commit，但未读取到代码明细，需补充 diff 证据"
    return "最近未识别到代码提交"


def _project_missing_modules(activity: RepositoryActivity) -> str:
    issues = activity.raw_data.get("issues", [])
    prs = activity.raw_data.get("pull_requests", [])
    candidates = []
    for item in issues[:3]:
        candidates.append("Issue #{0} {1}".format(item.get("number", "?"), item.get("title", "")))
    for item in prs[:3]:
        candidates.append("PR #{0} {1}".format(item.get("number", "?"), item.get("title", "")))
    if candidates:
        return "；".join(candidates)
    return "未从开放 Issue/PR 中识别明确待补模块"


def _project_risks(risks) -> str:
    if not risks:
        return "暂无明显内置风险信号"
    return "；".join("[{0}] {1}: {2}".format(risk.severity, risk.signal, risk.basis) for risk in risks[:3])


def _details_by_sha(details: List[Dict]) -> Dict[str, Dict]:
    result: Dict[str, Dict] = {}
    for item in details:
        sha = _commit_sha(item)
        if sha:
            result[sha] = item
    return result


def _commit_sha(item: Dict) -> str:
    return str(item.get("sha") or item.get("id") or "")[:8]


def _add_code_summary(employee: EmployeeSummary, detail: Dict) -> None:
    summary = summarize_code_changes([detail], max_patch_chars=0)
    employee.code_files += summary.file_count
    employee.additions += summary.additions
    employee.deletions += summary.deletions
    for key, value in summary.by_category.items():
        employee.code_categories[key] = employee.code_categories.get(key, 0) + value


def _error_lines(activities: List[RepositoryActivity]) -> str:
    lines: List[str] = []
    for item in activities:
        for error in item.errors:
            lines.append("- {0}: {1}".format(_repo_name(item.repo), error))
    return "\n".join(lines)


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... (context truncated)"
