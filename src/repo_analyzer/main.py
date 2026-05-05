"""repo-analyzer v1.2.0 —— 管理者侧 Gitea 仓库分析工具，支持单仓库、详细工作日志和多仓库管理者日报三种模式。"""

import argparse
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from org_memory.domain import IngestResult
from org_memory.extraction import RuleFactExtractor
from org_memory.ingest import build_gitea_ingest_result
from org_memory.store import LocalSQLiteMemoryStore, apply_ingest_result

from .analyzer import AIAnalysisError, run_ai_analysis, run_detail_worklog_analysis, run_work_summary_analysis
from .config_loader import get_default_model_config
from .data_builder import build_analysis_context, classify_commits
from .detail import (
    build_detail_raw_report,
    build_detail_worklog_context,
    classify_detail_commits,
    collect_file_snapshot_targets,
    filter_detail_data,
    format_detail_ai_report,
)
from .gitea_client import (
    GiteaClient,
    RepoRef,
    fetch_branches,
    fetch_commit_detail,
    fetch_commits,
    fetch_file_content,
    fetch_issues,
    fetch_pull_requests,
    list_repositories,
    parse_repo_url,
)
from .history import (
    build_history_snapshot,
    resolve_history_dir,
    save_history_snapshot,
)
from .manager import (
    RepositoryActivity,
    build_manager_work_summary_context,
    build_employee_summaries,
    build_manager_raw_report,
    format_manager_work_summary_report,
)
from .output import build_raw_report, format_ai_report, render_report
from .project_context import fetch_project_context_documents


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """解析 CLI 参数，返回 Namespace 对象。支持单仓库、详细日志和多仓库三种运行模式。"""
    parser = argparse.ArgumentParser(description="Gitea repository analyzer")
    parser.add_argument("--repo-url", help="single Gitea repository URL")
    parser.add_argument("--base-url", help="Gitea base URL, for --all-repos")
    parser.add_argument("--all-repos", action="store_true", help="scan all repositories visible to GITEA_TOKEN")
    parser.add_argument("--detail", action="store_true", help="generate a detailed AI work log for selected repository content")
    parser.add_argument("--scan-only", action="store_true", help="detail mode: output scan evidence without AI summary")
    parser.add_argument("--repo-query", default="", help="optional repository search keyword")
    parser.add_argument("--author", default=None, help="detail mode author filter")
    parser.add_argument("--path-filter", action="append", default=[], help="detail mode changed-file path filter; can be repeated")
    parser.add_argument("--commit", action="append", default=[], help="detail mode commit sha/prefix filter; can be repeated")
    parser.add_argument("--repo-limit", type=int, default=None, help="maximum repositories to scan")
    parser.add_argument("--group-by", choices=("employee",), default="employee", help="manager report grouping mode")
    parser.add_argument("--days", type=int, default=7, help="analyze recent N days")
    parser.add_argument("--branch", default=None, help="target branch; all-repos mode uses each repo default when omitted")
    parser.add_argument("--output", "-o", default=None, help="write Markdown report to file")
    parser.add_argument("--write-memory", action="store_true", help="write scanned evidence into org_memory SQLite store")
    parser.add_argument("--memory-db", default=None, help="org_memory SQLite path; default is data/org_memory.sqlite")
    parser.add_argument("--no-ai", action="store_true", help="skip AI analysis")
    parser.add_argument("--ai-timeout", type=int, default=None, help="AI request timeout seconds; default is 300")
    parser.add_argument("--no-code-context", action="store_true", help="skip commit file/stat/patch detail fetching")
    parser.add_argument("--code-commit-limit", type=int, default=10, help="maximum commits per repository to fetch code details for")
    parser.add_argument("--max-files-per-commit", type=int, default=12, help="maximum changed files to show per repository")
    parser.add_argument("--max-patch-chars", type=int, default=1200, help="maximum patch excerpt characters per repository")
    parser.add_argument("--no-file-content", action="store_true", help="detail mode: skip fetching changed-file content snapshots")
    parser.add_argument("--max-file-snapshots", type=int, default=8, help="detail mode: maximum changed files to fetch content for")
    parser.add_argument("--max-file-content-chars", type=int, default=2500, help="detail mode: maximum characters per fetched file content snapshot")
    parser.add_argument("--no-history", action="store_true", help="do not load or save report history")
    parser.add_argument("--history-dir", default=None, help="directory for manager report history snapshots")
    parser.add_argument("--history-limit", type=int, default=5, help="previous snapshots to include in analysis")
    parser.add_argument("--max-commits", type=int, default=50, help="maximum commits per repository")
    parser.add_argument("--workers", type=int, default=4, help="parallel repository fetch workers")
    parser.add_argument("--verbose", "-v", action="store_true", help="enable verbose logs")
    return parser.parse_args(argv)


def validate_args(args: argparse.Namespace) -> None:
    """校验 CLI 参数的合法性，不合法时抛出 ValueError。"""
    if not os.environ.get("GITEA_TOKEN"):
        raise ValueError("environment variable GITEA_TOKEN is required")
    if args.days < 1:
        raise ValueError("days must be greater than 0")
    if args.max_commits < 1:
        raise ValueError("max-commits must be greater than 0")
    if getattr(args, "workers", 4) < 1:
        raise ValueError("workers must be greater than 0")
    if getattr(args, "repo_limit", None) is not None and args.repo_limit < 1:
        raise ValueError("repo-limit must be greater than 0")
    if getattr(args, "code_commit_limit", 10) < 0:
        raise ValueError("code-commit-limit must not be negative")
    if getattr(args, "max_files_per_commit", 12) < 1:
        raise ValueError("max-files-per-commit must be greater than 0")
    if getattr(args, "max_patch_chars", 1200) < 0:
        raise ValueError("max-patch-chars must not be negative")
    if getattr(args, "ai_timeout", None) is not None and args.ai_timeout < 1:
        raise ValueError("ai-timeout must be greater than 0")
    if getattr(args, "history_limit", 5) < 0:
        raise ValueError("history-limit must not be negative")
    if getattr(args, "max_file_snapshots", 8) < 0:
        raise ValueError("max-file-snapshots must not be negative")
    if getattr(args, "max_file_content_chars", 2500) < 0:
        raise ValueError("max-file-content-chars must not be negative")

    if getattr(args, "all_repos", False):
        args.base_url = (args.base_url or os.environ.get("GITEA_BASE_URL") or "").rstrip("/")
        _validate_http_url(args.base_url, "base-url")
        return

    if getattr(args, "detail", False) and not getattr(args, "repo_url", None):
        raise ValueError("repo-url is required for --detail")
    if not getattr(args, "repo_url", None):
        raise ValueError("repo-url is required unless --all-repos is used")
    _validate_http_url(args.repo_url, "repo-url")


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    )


def fetch_all_data(
    repo_url: str,
    branch: Optional[str],
    days: int,
    max_commits: int = 50,
    include_code: bool = True,
    code_commit_limit: Optional[int] = None,
) -> Tuple[Dict, List[str]]:
    """获取单个仓库的所有数据（提交、Issue、PR、分支、项目文档），返回 (raw_data, errors)。"""
    ref = parse_repo_url(repo_url)
    token = os.environ["GITEA_TOKEN"]
    client = GiteaClient(ref.base_url, token)
    selected_branch = branch or "main"
    results, errors = _fetch_repo_sources(
        client,
        ref,
        selected_branch,
        days,
        max_commits,
        include_code=include_code,
        code_commit_limit=code_commit_limit if code_commit_limit is not None else max_commits,
    )
    if not any(results.values()):
        raise RuntimeError("all data sources failed; cannot generate report")
    return results, errors


def fetch_manager_activities(args: argparse.Namespace) -> List[RepositoryActivity]:
    """并行获取所有可见仓库的活动数据，返回按仓库名排序的 RepositoryActivity 列表。

    使用 ThreadPoolExecutor 并行拉取，单个仓库失败时记录警告并继续处理其他仓库。
    """
    token = os.environ["GITEA_TOKEN"]
    discovery_client = GiteaClient(args.base_url, token)
    repos = list_repositories(discovery_client, query=args.repo_query, limit=args.repo_limit)
    if not repos:
        raise RuntimeError("no repositories found for the current GITEA_TOKEN")

    activities: List[RepositoryActivity] = []
    max_workers = min(args.workers, max(1, len(repos)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                fetch_repository_activity,
                repo,
                args.branch,
                args.days,
                args.max_commits,
                not args.no_code_context,
                args.code_commit_limit,
            ): repo
            for repo in repos
        }
        for future in as_completed(futures):
            repo = futures[future]
            try:
                activities.append(future.result())
            except Exception as exc:
                logging.warning("repository fetch failed: %s/%s: %s", repo.owner, repo.repo, exc)
                activities.append(
                    RepositoryActivity(
                        repo=repo,
                        branch=args.branch or repo.default_branch or "main",
                        raw_data=_empty_raw_data(),
                        classified=[],
                        errors=["repository: {0}".format(exc)],
                    )
                )

    return sorted(activities, key=lambda item: item.repo.full_name or "{0}/{1}".format(item.repo.owner, item.repo.repo))


def fetch_repository_activity(
    repo: RepoRef,
    branch: Optional[str],
    days: int,
    max_commits: int,
    include_code: bool = True,
    code_commit_limit: int = 10,
) -> RepositoryActivity:
    """获取单个仓库的活动数据并分类提交，供管理者报告使用。"""
    token = os.environ["GITEA_TOKEN"]
    client = GiteaClient(repo.base_url, token)
    selected_branch = branch or repo.default_branch or "main"
    raw_data, errors = _fetch_repo_sources(
        client,
        repo,
        selected_branch,
        days,
        max_commits,
        include_code=include_code,
        code_commit_limit=code_commit_limit,
    )
    classified = classify_commits(raw_data.get("commits", []))
    return RepositoryActivity(
        repo=repo,
        branch=selected_branch,
        raw_data=raw_data,
        classified=classified,
        errors=errors,
    )


def run(argv: Optional[List[str]] = None) -> int:
    """主入口：解析参数，根据模式分发到对应的报告生成流程，返回退出码。"""
    try:
        args = parse_args(argv)
        setup_logging(args.verbose)
        validate_args(args)

        if args.detail:
            report = _run_detail_report(args)
        elif args.all_repos:
            report = _run_manager_report(args)
        else:
            report = _run_single_repo_report(args)

        render_report(report, args.output)
        return 0
    except Exception as exc:
        logging.error("program failed: %s", exc)
        return 1


def _run_single_repo_report(args: argparse.Namespace) -> str:
    selected_branch = args.branch or "main"
    args.branch = selected_branch
    raw_data, errors = fetch_all_data(
        args.repo_url,
        selected_branch,
        args.days,
        args.max_commits,
        include_code=not args.no_code_context,
        code_commit_limit=args.code_commit_limit,
    )
    classified = classify_commits(raw_data.get("commits", []))
    if args.write_memory:
        _write_activities_to_memory(
            [_activity_from_single_repo(args.repo_url, selected_branch, raw_data, classified, errors)],
            args,
        )

    if args.no_ai:
        return build_raw_report(classified, raw_data, errors, args)

    try:
        model_config = _get_model_config(args)
        context = build_analysis_context(classified, raw_data, args)
        analysis = run_ai_analysis(context, model_config)
        return format_ai_report(analysis, classified, raw_data, errors, args)
    except (AIAnalysisError, FileNotFoundError, ValueError) as exc:
        logging.warning("AI analysis failed; falling back to raw report: %s", exc)
        return build_raw_report(classified, raw_data, errors, args)


def _run_detail_report(args: argparse.Namespace) -> str:
    selected_branch = args.branch or "main"
    args.branch = selected_branch
    raw_data, errors = fetch_all_data(
        args.repo_url,
        selected_branch,
        args.days,
        args.max_commits,
        include_code=True,
        code_commit_limit=args.max_commits,
    )
    filtered = filter_detail_data(
        raw_data,
        author=args.author,
        path_filters=args.path_filter,
        commit_filters=args.commit,
    )
    snapshot_errors: List[str] = []
    if not args.no_file_content and args.max_file_snapshots:
        snapshots, snapshot_errors = _fetch_file_snapshots(args.repo_url, filtered, args)
        filtered["file_snapshots"] = snapshots
    classified = classify_detail_commits(filtered)
    all_errors = errors + snapshot_errors
    if all_errors:
        filtered["errors"] = all_errors
    if args.write_memory:
        _write_activities_to_memory(
            [_activity_from_single_repo(args.repo_url, selected_branch, filtered, classified, all_errors)],
            args,
        )

    if args.no_ai or args.scan_only:
        return build_detail_raw_report(filtered, classified, args)

    try:
        model_config = _get_model_config(args)
        context = build_detail_worklog_context(filtered, classified, args)
        analysis = run_detail_worklog_analysis(context, model_config)
        return format_detail_ai_report(analysis, filtered, classified, args)
    except (AIAnalysisError, FileNotFoundError, ValueError) as exc:
        logging.warning("AI detail work log failed; falling back to raw detail report: %s", exc)
        return build_detail_raw_report(filtered, classified, args)


def _run_manager_report(args: argparse.Namespace) -> str:
    activities = fetch_manager_activities(args)
    if args.write_memory:
        _write_activities_to_memory(activities, args)
    employees = build_employee_summaries(activities)
    current_snapshot = build_history_snapshot(activities, employees, args)
    history_dir = resolve_history_dir(args.output, args.history_dir)
    if args.no_ai:
        report = build_manager_raw_report(activities, employees, args)
    else:
        try:
            model_config = _get_model_config(args)
            context = build_manager_work_summary_context(activities, employees, args)
            summary = run_work_summary_analysis(context, model_config)
            report = format_manager_work_summary_report(summary, activities, args)
        except (AIAnalysisError, FileNotFoundError, ValueError) as exc:
            logging.warning("AI work summary failed; falling back to rule-based report: %s", exc)
            report = build_manager_raw_report(activities, employees, args)
    if not args.no_history:
        save_history_snapshot(history_dir, current_snapshot, report)
    return report


def _activity_from_single_repo(
    repo_url: str,
    branch: str,
    raw_data: Dict,
    classified,
    errors: List[str],
) -> RepositoryActivity:
    return RepositoryActivity(
        repo=parse_repo_url(repo_url),
        branch=branch,
        raw_data=raw_data,
        classified=classified,
        errors=errors,
    )


def _write_activities_to_memory(activities: List[RepositoryActivity], args: argparse.Namespace) -> None:
    """将仓库活动数据写入 org_memory SQLite 数据库，同时运行规则提取器生成 facts 和 relationships。"""
    db_path = _resolve_memory_db_path(args)
    store = LocalSQLiteMemoryStore(str(db_path))
    extractor = RuleFactExtractor()
    for activity in activities:
        ingest = build_gitea_ingest_result(activity)
        extraction = extractor.extract(ingest.events)
        combined = IngestResult(
            entities=ingest.entities,
            sources=ingest.sources,
            events=ingest.events,
            facts=ingest.facts + extraction.facts,
            relationships=ingest.relationships + extraction.relationships,
        )
        apply_ingest_result(store, combined)
        repo_name = activity.repo.full_name or "{0}/{1}".format(activity.repo.owner, activity.repo.repo)
        store.audit(
            action="repo_analyzer_ingest",
            target_type="repo",
            target_id=repo_name,
            actor_id="system:repo_analyzer",
            reason="write-memory CLI option",
        )
        if extraction.errors:
            logging.warning("%s extraction warnings: %s", repo_name, "; ".join(extraction.errors))
    logging.info("org_memory wrote %s repository activities to %s", len(activities), db_path)


def _resolve_memory_db_path(args: argparse.Namespace) -> Path:
    if getattr(args, "memory_db", None):
        return Path(args.memory_db).expanduser()
    return Path(__file__).resolve().parents[2] / "data" / "org_memory.sqlite"


def _fetch_file_snapshots(repo_url: str, raw_data: Dict, args: argparse.Namespace) -> Tuple[List[Dict], List[str]]:
    ref = parse_repo_url(repo_url)
    client = GiteaClient(ref.base_url, os.environ["GITEA_TOKEN"])
    snapshots: List[Dict] = []
    errors: List[str] = []
    targets = collect_file_snapshot_targets(raw_data, getattr(args, "max_file_snapshots", 8))
    for target in targets:
        path = target["path"]
        commit_ref = target.get("ref") or getattr(args, "branch", None)
        try:
            content = fetch_file_content(client, ref.owner, ref.repo, path, ref=commit_ref)
            snapshots.append(
                {
                    "path": path,
                    "ref": commit_ref,
                    "content": (content.get("decoded_content") or "")[: getattr(args, "max_file_content_chars", 2500)],
                    "size": content.get("size"),
                    "encoding": content.get("encoding"),
                }
            )
        except Exception as exc:
            errors.append("file_content {0}@{1}: {2}".format(path, str(commit_ref)[:8], exc))
            snapshots.append({"path": path, "ref": commit_ref, "error": str(exc)})
    return snapshots, errors


def _get_model_config(args: argparse.Namespace) -> Dict:
    model_config = dict(get_default_model_config())
    if getattr(args, "ai_timeout", None) is not None:
        model_config["timeout"] = args.ai_timeout
    return model_config


def _fetch_repo_sources(
    client: GiteaClient,
    ref: RepoRef,
    branch: str,
    days: int,
    max_commits: int,
    include_code: bool = False,
    code_commit_limit: int = 10,
) -> Tuple[Dict, List[str]]:
    """并行拉取单个仓库的 commits/issues/PRs/branches 和项目文档，可选拉取 commit 代码详情。

    返回 (raw_data, errors)，errors 包含各数据源的非致命错误。
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    jobs = {
        "commits": lambda: fetch_commits(client, ref.owner, ref.repo, branch, since, max_commits, include_code),
        "issues": lambda: fetch_issues(client, ref.owner, ref.repo, "open"),
        "pull_requests": lambda: fetch_pull_requests(client, ref.owner, ref.repo, "open"),
        "branches": lambda: fetch_branches(client, ref.owner, ref.repo),
    }
    results = _empty_raw_data()
    errors: List[str] = []
    project_context, project_context_errors = fetch_project_context_documents(client, ref, branch)
    results["project_context"] = project_context
    errors.extend(project_context_errors)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(func): name for name, func in jobs.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as exc:
                errors.append("{0}: {1}".format(name, exc))
                logging.warning("%s/%s %s fetch failed: %s", ref.owner, ref.repo, name, exc)
    if include_code and results.get("commits") and code_commit_limit:
        details, detail_errors = _fetch_commit_details(
            client,
            ref,
            results["commits"][:code_commit_limit],
            include_code=True,
        )
        results["commit_details"] = details
        errors.extend(detail_errors)
    return results, errors


def _empty_raw_data() -> Dict[str, List[Dict]]:
    return {
        "commits": [],
        "issues": [],
        "pull_requests": [],
        "branches": [],
        "commit_details": [],
        "project_context": [],
    }


def _fetch_commit_details(
    client: GiteaClient,
    ref: RepoRef,
    commits: List[Dict],
    include_code: bool,
) -> Tuple[List[Dict], List[str]]:
    """逐个获取 commit 的代码详情（文件变更和 patch），已有详情的 commit 直接复用。"""
    details: List[Dict] = []
    errors: List[str] = []
    for item in commits:
        sha = item.get("sha") or item.get("id")
        if not sha:
            continue
        if item.get("files") or item.get("stats"):
            details.append(item)
            continue
        try:
            detail = fetch_commit_detail(client, ref.owner, ref.repo, sha, include_code=include_code)
            if detail:
                details.append(detail)
        except Exception as exc:
            errors.append("commit_detail {0}: {1}".format(str(sha)[:8], exc))
            logging.warning("%s/%s commit detail fetch failed: %s", ref.owner, ref.repo, exc)
    return details, errors


def _validate_http_url(value: str, name: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("{0} must be a valid http/https URL".format(name))


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
