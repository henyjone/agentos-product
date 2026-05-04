import argparse
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .analyzer import AIAnalysisError, run_ai_analysis
from .config_loader import get_default_model_config
from .data_builder import build_analysis_context, classify_commits
from .gitea_client import (
    GiteaClient,
    RepoRef,
    fetch_branches,
    fetch_commit_detail,
    fetch_commits,
    fetch_issues,
    fetch_pull_requests,
    list_repositories,
    parse_repo_url,
)
from .history import (
    build_history_context,
    build_history_report,
    build_history_snapshot,
    load_history_snapshots,
    resolve_history_dir,
    save_history_snapshot,
)
from .manager import (
    RepositoryActivity,
    build_employee_summaries,
    build_manager_analysis_context,
    build_manager_raw_report,
    format_manager_ai_report,
)
from .output import build_raw_report, format_ai_report, render_report


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gitea repository analyzer")
    parser.add_argument("--repo-url", help="single Gitea repository URL")
    parser.add_argument("--base-url", help="Gitea base URL, for --all-repos")
    parser.add_argument("--all-repos", action="store_true", help="scan all repositories visible to GITEA_TOKEN")
    parser.add_argument("--repo-query", default="", help="optional repository search keyword")
    parser.add_argument("--repo-limit", type=int, default=None, help="maximum repositories to scan")
    parser.add_argument("--group-by", choices=("employee",), default="employee", help="manager report grouping mode")
    parser.add_argument("--days", type=int, default=7, help="analyze recent N days")
    parser.add_argument("--branch", default=None, help="target branch; all-repos mode uses each repo default when omitted")
    parser.add_argument("--output", "-o", default=None, help="write Markdown report to file")
    parser.add_argument("--no-ai", action="store_true", help="skip AI analysis")
    parser.add_argument("--no-code-context", action="store_true", help="skip commit file/stat/patch detail fetching")
    parser.add_argument("--code-commit-limit", type=int, default=10, help="maximum commits per repository to fetch code details for")
    parser.add_argument("--max-files-per-commit", type=int, default=12, help="maximum changed files to show per repository")
    parser.add_argument("--max-patch-chars", type=int, default=1200, help="maximum patch excerpt characters per repository")
    parser.add_argument("--no-history", action="store_true", help="do not load or save report history")
    parser.add_argument("--history-dir", default=None, help="directory for manager report history snapshots")
    parser.add_argument("--history-limit", type=int, default=5, help="previous snapshots to include in analysis")
    parser.add_argument("--max-commits", type=int, default=50, help="maximum commits per repository")
    parser.add_argument("--workers", type=int, default=4, help="parallel repository fetch workers")
    parser.add_argument("--verbose", "-v", action="store_true", help="enable verbose logs")
    return parser.parse_args(argv)


def validate_args(args: argparse.Namespace) -> None:
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
    if getattr(args, "history_limit", 5) < 0:
        raise ValueError("history-limit must not be negative")

    if getattr(args, "all_repos", False):
        args.base_url = (args.base_url or os.environ.get("GITEA_BASE_URL") or "").rstrip("/")
        _validate_http_url(args.base_url, "base-url")
        return

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
    try:
        args = parse_args(argv)
        setup_logging(args.verbose)
        validate_args(args)

        if args.all_repos:
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

    if args.no_ai:
        return build_raw_report(classified, raw_data, errors, args)

    try:
        model_config = get_default_model_config()
        context = build_analysis_context(classified, raw_data, args)
        analysis = run_ai_analysis(context, model_config)
        return format_ai_report(analysis, classified, raw_data, errors, args)
    except (AIAnalysisError, FileNotFoundError, ValueError) as exc:
        logging.warning("AI analysis failed; falling back to raw report: %s", exc)
        return build_raw_report(classified, raw_data, errors, args)


def _run_manager_report(args: argparse.Namespace) -> str:
    activities = fetch_manager_activities(args)
    employees = build_employee_summaries(activities)
    current_snapshot = build_history_snapshot(activities, employees, args)
    history_dir = resolve_history_dir(args.output, args.history_dir)
    history_items = [] if args.no_history else load_history_snapshots(history_dir, args.history_limit)
    history_context = build_history_context(history_items, current_snapshot)
    history_report = build_history_report(history_items, current_snapshot)

    if args.no_ai:
        report = build_manager_raw_report(activities, employees, args, history_report=history_report)
        if not args.no_history:
            save_history_snapshot(history_dir, current_snapshot, report)
        return report

    try:
        model_config = get_default_model_config()
        context = build_manager_analysis_context(activities, employees, args, history_context=history_context)
        analysis = run_ai_analysis(context, model_config)
        report = format_manager_ai_report(analysis, activities, employees, args, history_report=history_report)
    except (AIAnalysisError, FileNotFoundError, ValueError) as exc:
        logging.warning("AI analysis failed; falling back to raw manager report: %s", exc)
        report = build_manager_raw_report(activities, employees, args, history_report=history_report)
    if not args.no_history:
        save_history_snapshot(history_dir, current_snapshot, report)
    return report


def _fetch_repo_sources(
    client: GiteaClient,
    ref: RepoRef,
    branch: str,
    days: int,
    max_commits: int,
    include_code: bool = False,
    code_commit_limit: int = 10,
) -> Tuple[Dict, List[str]]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    jobs = {
        "commits": lambda: fetch_commits(client, ref.owner, ref.repo, branch, since, max_commits, include_code),
        "issues": lambda: fetch_issues(client, ref.owner, ref.repo, "open"),
        "pull_requests": lambda: fetch_pull_requests(client, ref.owner, ref.repo, "open"),
        "branches": lambda: fetch_branches(client, ref.owner, ref.repo),
    }
    results = _empty_raw_data()
    errors: List[str] = []

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
    return {"commits": [], "issues": [], "pull_requests": [], "branches": [], "commit_details": []}


def _fetch_commit_details(
    client: GiteaClient,
    ref: RepoRef,
    commits: List[Dict],
    include_code: bool,
) -> Tuple[List[Dict], List[str]]:
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
