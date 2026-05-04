import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


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
        ["git"] + args,
        cwd=path,
        text=True,
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


def get_staged_diff(path: str = ".", max_bytes: int = 8000) -> str:
    """返回暂存区的 diff 文本，截断到 max_bytes 避免超出模型上下文。"""
    result = _run_git(["diff", "--cached", "--unified=3"], path)
    if result.returncode != 0 or not result.stdout.strip():
        return ""
    diff = result.stdout
    if len(diff.encode("utf-8")) > max_bytes:
        diff = diff.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
        diff += "\n... (diff truncated)"
    return diff


def execute_commit(message: str, path: str = ".") -> CommitResult:
    result = _run_git(["commit", "-m", message], path)
    if result.returncode != 0:
        return CommitResult(success=False, error_message=result.stderr.strip())
    return CommitResult(success=True, sha=get_last_commit_sha(path))


def execute_push(path: str = ".") -> bool:
    """推送当前分支到远程。返回是否成功。"""
    result = _run_git(["push"], path)
    return result.returncode == 0

