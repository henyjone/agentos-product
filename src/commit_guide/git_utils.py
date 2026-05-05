"""Git 操作工具模块 —— 封装 subprocess 调用，提供仓库状态查询、diff 构建和提交推送功能。"""

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


# 用于判断文件是否属于"代码文件"的扩展名集合，影响 diff 优先级排序
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
    """当前仓库的工作区状态快照。"""

    repo_name: str        # 仓库目录名
    branch: str           # 当前分支名
    staged: List[str]     # 已暂存（index）的文件列表
    unstaged: List[str]   # 已修改但未暂存的文件列表
    untracked: List[str]  # 未跟踪的新文件列表

    @property
    def has_staged(self) -> bool:
        """暂存区是否有待提交的文件。"""
        return bool(self.staged)


@dataclass(frozen=True)
class CommitResult:
    """git commit 执行结果。"""

    success: bool
    sha: Optional[str] = None           # 提交成功时的完整 SHA
    error_message: Optional[str] = None  # 失败时的 stderr 内容


def _run_git(args: List[str], path: str = ".") -> subprocess.CompletedProcess:
    """在指定目录执行 git 命令，禁用 quotepath 以正确处理中文路径。"""
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
    """检查系统 PATH 中是否存在可用的 git 命令。"""
    try:
        result = _run_git(["--version"])
        return result.returncode == 0
    except FileNotFoundError:
        return False


def is_git_repo(path: str = ".") -> bool:
    """判断指定路径是否在 git 仓库内。"""
    result = _run_git(["rev-parse", "--git-dir"], path)
    return result.returncode == 0


def _stdout_lines(result: subprocess.CompletedProcess) -> List[str]:
    """从 CompletedProcess 中提取非空行列表；命令失败或无输出时返回空列表。"""
    if result.returncode != 0 or not result.stdout.strip():
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def get_repo_status(path: str = ".") -> GitStatus:
    """获取仓库当前工作区状态，包括分支名、暂存/未暂存/未跟踪文件列表。"""
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
    """获取最新提交的完整 SHA，仓库无提交时返回 None。"""
    result = _run_git(["rev-parse", "HEAD"], path)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def get_remotes(path: str = ".") -> List[str]:
    """返回仓库配置的所有 remote 名称列表。"""
    result = _run_git(["remote"], path)
    return _stdout_lines(result)


def get_staged_diff(path: str = ".", max_bytes: int = 24000) -> str:
    """构建供 AI 分析的暂存区变更上下文，按文件类型优先级排序后截断。

    直接使用全局 diff 会从头截断，当大型文档排在代码文件前面时，
    模型将看不到代码变更。本函数保留完整文件列表和 stat，
    再按代码文件优先的顺序逐文件附加 diff 片段。
    """
    files = _stdout_lines(_run_git(["diff", "--cached", "--name-only"], path))
    if not files:
        return ""

    stat = _run_git(["diff", "--cached", "--stat"], path).stdout.strip()
    numstat = _run_git(["diff", "--cached", "--numstat"], path).stdout.strip()
    # 按优先级排序：源码 > 测试 > 其他 > 文档
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

    # 计算每个文件可用的字节预算，确保代码文件至少有 900 字节
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
    """返回文件的排序优先级元组：(group, path)，group 越小越靠前。

    group 0 = 源码文件（非测试）
    group 1 = 测试文件
    group 2 = 其他文件
    group 3 = 文档文件
    """
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
    """按字节数截断文本，保证 UTF-8 编码不超过 max_bytes。"""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore") + "\n... (truncated)"


def execute_add(patterns: List[str], path: str = ".") -> tuple:
    """暂存匹配指定 pattern 的文件。返回 (success, stderr_detail)。"""
    result = _run_git(["add", "--"] + patterns, path)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "").strip()
    return True, ""


def execute_commit(message: str, path: str = ".") -> CommitResult:
    """执行 git commit，成功时返回包含新 SHA 的 CommitResult。"""
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
    """推送当前分支到远端，失败时自动重试。返回 (success, stderr_detail)。

    部分内网 Gitea 部署会间歇性拒绝首次 HTTP 认证请求，
    重试机制可在不影响用户体验的前提下规避此问题。
    """
    args = ["push"]
    if remote:
        args.append(remote)
        # branch 为 HEAD 或 unknown 时不显式指定，避免推送到错误分支
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
