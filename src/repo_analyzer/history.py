import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .code_context import summarize_code_changes
from .manager import EmployeeSummary, RepositoryActivity, build_manager_overview


SCHEMA_VERSION = 1


def resolve_history_dir(output_path: Optional[str], explicit_history_dir: Optional[str] = None) -> Path:
    if explicit_history_dir:
        return Path(explicit_history_dir)
    if output_path:
        return Path(output_path).resolve().parent / "history"
    return Path.cwd() / "reports" / "history"


def load_history_snapshots(history_dir: Path, limit: int = 5) -> List[Dict]:
    if limit <= 0 or not history_dir.exists():
        return []
    snapshots: List[Dict] = []
    for path in sorted(history_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("schema_version") == SCHEMA_VERSION:
            data["_path"] = str(path)
            snapshots.append(data)
        if len(snapshots) >= limit:
            break
    return snapshots


def build_history_snapshot(
    activities: List[RepositoryActivity],
    employees: List[EmployeeSummary],
    args,
) -> Dict:
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    overview = build_manager_overview(activities)
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": created_at,
        "base_url": getattr(args, "base_url", ""),
        "days": getattr(args, "days", 7),
        "overview": overview,
        "employees": [
            {
                "identity": item.identity,
                "commits": item.commits,
                "open_issues": item.open_issues,
                "open_prs": item.open_prs,
                "repos": sorted(item.repos),
                "commit_types": dict(item.commit_types),
                "latest_activity": item.latest_activity,
            }
            for item in employees
        ],
        "repositories": [_repo_snapshot(item, getattr(args, "days", 7)) for item in activities],
    }


def save_history_snapshot(history_dir: Path, snapshot: Dict, report: str) -> Path:
    history_dir.mkdir(parents=True, exist_ok=True)
    stamp = _stamp(snapshot.get("created_at", ""))
    json_path = history_dir / "{0}.json".format(stamp)
    md_path = history_dir / "{0}.md".format(stamp)
    counter = 2
    while json_path.exists() or md_path.exists():
        json_path = history_dir / "{0}-{1}.json".format(stamp, counter)
        md_path = history_dir / "{0}-{1}.md".format(stamp, counter)
        counter += 1
    json_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    md_path.write_text(report, encoding="utf-8")
    return json_path


def build_history_context(history: List[Dict], current: Optional[Dict] = None) -> str:
    if not history:
        return "- No previous snapshots."
    lines = ["Previous snapshots loaded: {0}".format(len(history))]
    previous = history[0]
    lines.extend(_delta_lines(previous, current))
    lines.extend(["", "Recent snapshot table:", "| Time | Repos | Commits | Code commits | Issues | PRs |", "|---|---:|---:|---:|---:|---:|"])
    for item in history:
        overview = item.get("overview", {}) or {}
        lines.append(
            "| {0} | {1} | {2} | {3} | {4} | {5} |".format(
                item.get("created_at", "")[:19],
                overview.get("repo_count", 0),
                overview.get("commit_count", 0),
                overview.get("code_commit_count", 0),
                overview.get("open_issue_count", 0),
                overview.get("open_pr_count", 0),
            )
        )
    lines.extend(["", "Previous top employees:"])
    for employee in (previous.get("employees") or [])[:10]:
        lines.append(
            "- {0}: commits={1}, issues={2}, prs={3}, repos={4}".format(
                employee.get("identity", "unknown"),
                employee.get("commits", 0),
                employee.get("open_issues", 0),
                employee.get("open_prs", 0),
                ", ".join(employee.get("repos") or []),
            )
        )
    return "\n".join(lines)


def build_history_report(history: List[Dict], current: Optional[Dict] = None) -> str:
    if not history:
        return "- 没有加载到历史快照。"
    previous = history[0]
    lines = [
        "- 已加载历史快照: {0} 个".format(len(history)),
        "- 最近一次历史快照: {0}".format(previous.get("created_at", "")[:19]),
    ]
    lines.extend(_delta_lines(previous, current, chinese=True))
    lines.extend(["", "| 时间 | 仓库 | Commit | 代码明细 Commit | Issue | PR |", "|---|---:|---:|---:|---:|---:|"])
    for item in history:
        overview = item.get("overview", {}) or {}
        lines.append(
            "| {0} | {1} | {2} | {3} | {4} | {5} |".format(
                item.get("created_at", "")[:19],
                overview.get("repo_count", 0),
                overview.get("commit_count", 0),
                overview.get("code_commit_count", 0),
                overview.get("open_issue_count", 0),
                overview.get("open_pr_count", 0),
            )
        )
    return "\n".join(lines)


def _repo_snapshot(activity: RepositoryActivity, days: int) -> Dict:
    from .data_builder import compute_stats, identify_builtin_risks

    stats = compute_stats(activity.classified)
    risks = identify_builtin_risks(activity.classified, activity.raw_data, days)
    code = summarize_code_changes(activity.raw_data.get("commit_details", []), max_patch_chars=0)
    return {
        "name": activity.repo.full_name or "{0}/{1}".format(activity.repo.owner, activity.repo.repo),
        "branch": activity.branch,
        "commits": stats.total,
        "format_compliance_rate": stats.format_compliance_rate,
        "open_issues": len(activity.raw_data.get("issues", [])),
        "open_prs": len(activity.raw_data.get("pull_requests", [])),
        "code_files": code.file_count,
        "additions": code.additions,
        "deletions": code.deletions,
        "code_categories": dict(code.by_category),
        "risks": [risk.signal for risk in risks],
        "errors": list(activity.errors),
    }


def _delta_lines(previous: Dict, current: Optional[Dict], chinese: bool = False) -> List[str]:
    if not current:
        return []
    previous_overview = previous.get("overview", {}) or {}
    current_overview = current.get("overview", {}) or {}
    fields = [
        ("repo_count", "仓库" if chinese else "repos"),
        ("commit_count", "Commit" if chinese else "commits"),
        ("code_commit_count", "代码明细 Commit" if chinese else "code commits"),
        ("open_issue_count", "开放 Issue" if chinese else "open issues"),
        ("open_pr_count", "开放 PR" if chinese else "open PRs"),
    ]
    prefix = "- 相比最近一次历史快照" if chinese else "- Delta vs previous"
    return [
        "{0}: {1} {2:+d}".format(
            prefix,
            label,
            int(current_overview.get(key, 0)) - int(previous_overview.get(key, 0)),
        )
        for key, label in fields
    ]


def _stamp(value: str) -> str:
    if value:
        return value.replace(":", "").replace("-", "").replace("+0000", "Z")[:15].replace("T", "-")
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
