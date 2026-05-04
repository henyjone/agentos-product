import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


_CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".go",
    ".rs",
    ".cpp",
    ".c",
    ".h",
    ".cs",
    ".sql",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
}


@dataclass(frozen=True)
class GitStatus:
    repo_name: str
    branch: str
    staged: List[str]
    unstaged: List[str]
    untracked: List[str]

    @property
    def has_staged(self) -> bool:
        return bool(self.staged)


@dataclass(frozen=True)
class CommitResult:
    success: bool
    sha: Optional[str] = None
    error_message: Optional[str] = None


def _run_git(args: List[str], path: str = ".") -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "core.quotepath=false"] + args,
        cwd=path,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
    )


def check_git_available() -> bool:
    try:
        result = _run_git(["--version"])
        return result.returncode == 0
    except FileNotFoundError:
        return False


def is_git_repo(path: str = ".") -> bool:
    result = _run_git(["rev-parse", "--git-dir"], path)
    return result.returncode == 0


def _stdout_lines(result: subprocess.CompletedProcess) -> List[str]:
    if result.returncode != 0 or not result.stdout.strip():
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def get_repo_status(path: str = ".") -> GitStatus:
    if not is_git_repo(path):
        raise RuntimeError("current path is not a git repository")

    branch_result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], path)
    staged = _stdout_lines(_run_git(["diff", "--name-only", "--cached"], path))
    unstaged = _stdout_lines(_run_git(["diff", "--name-only"], path))
    untracked = _stdout_lines(
        _run_git(["ls-files", "--others", "--exclude-standard"], path)
    )

    repo_name = Path(path).resolve().name
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"
    return GitStatus(
        repo_name=repo_name,
        branch=branch,
        staged=staged,
        unstaged=unstaged,
        untracked=untracked,
    )


def get_last_commit_sha(path: str = ".") -> Optional[str]:
    result = _run_git(["rev-parse", "HEAD"], path)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def get_remotes(path: str = ".") -> List[str]:
    """Return configured git remote names."""
    result = _run_git(["remote"], path)
    return _stdout_lines(result)


def get_staged_diff(path: str = ".", max_bytes: int = 24000) -> str:
    """Build a balanced staged-change context for AI.

    A single global diff truncates from the beginning. When many large docs are
    staged before code files, the model never sees the code changes. This
    context keeps the full file list/stat and includes bounded per-file snippets
    with code files first.
    """
    files = _stdout_lines(_run_git(["diff", "--cached", "--name-only"], path))
    if not files:
        return ""

    stat = _run_git(["diff", "--cached", "--stat"], path).stdout.strip()
    numstat = _run_git(["diff", "--cached", "--numstat"], path).stdout.strip()
    ordered_files = sorted(files, key=_file_priority)

    sections = [
        "## Staged files",
        "\n".join("- {0}".format(item) for item in files),
        "",
        "## Change stat",
        stat,
        "",
        "## Numstat",
        numstat,
        "",
        "## Selected per-file diff snippets",
    ]

    header_bytes = len("\n".join(sections).encode("utf-8"))
    remaining = max(4000, max_bytes - header_bytes)
    per_file_budget = max(900, remaining // max(len(ordered_files), 1))

    for file_path in ordered_files:
        diff_result = _run_git(
            ["diff", "--cached", "--unified=2", "--", file_path],
            path,
        )
        snippet = diff_result.stdout.strip()
        if not snippet:
            continue
        snippet = _truncate_bytes(snippet, per_file_budget)
        sections.extend(
            [
                "",
                "### {0}".format(file_path),
                snippet,
            ]
        )

    context = "\n".join(sections).strip()
    return _truncate_bytes(context, max_bytes)


def _file_priority(file_path: str) -> tuple:
    path = Path(file_path)
    suffix = path.suffix.lower()
    normalized = file_path.replace("\\", "/").lower()
    if suffix in _CODE_EXTENSIONS and "/tests/" not in normalized:
        group = 0
    elif "/tests/" in normalized or normalized.startswith("tests/"):
        group = 1
    elif suffix in {".md", ".rst", ".txt"} or normalized.startswith("docs/"):
        group = 3
    else:
        group = 2
    return (group, file_path)


def _truncate_bytes(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore") + "\n... (truncated)"


def execute_commit(message: str, path: str = ".") -> CommitResult:
    result = _run_git(["commit", "-m", message], path)
    if result.returncode != 0:
        return CommitResult(success=False, error_message=result.stderr.strip())
    return CommitResult(success=True, sha=get_last_commit_sha(path))


def execute_push(
    path: str = ".",
    remote: Optional[str] = None,
    branch: Optional[str] = None,
    max_attempts: int = 3,
    retry_delay_seconds: float = 1.0,
) -> tuple:
    """Push current branch. Returns (success, stderr_detail).

    Some internal Gitea deployments intermittently reject the first HTTP
    authentication attempt. Retrying here keeps the CLI friendly while still
    returning the final Git error when all attempts fail.
    """
    args = ["push"]
    if remote:
        args.append(remote)
        if branch and branch not in ("HEAD", "unknown"):
            args.append(branch)
    attempts = max(1, max_attempts)
    last_detail = ""
    for attempt in range(1, attempts + 1):
        result = _run_git(args, path)
        if result.returncode == 0:
            return True, ""
        last_detail = (result.stderr or result.stdout or "").strip()
        if attempt < attempts and retry_delay_seconds > 0:
            time.sleep(retry_delay_seconds)
    if attempts > 1:
        return False, "已重试 {0} 次，最后错误: {1}".format(attempts, last_detail or "未知错误")
    return False, last_detail
