"""commit-guide v2.0 —— AI 读取 diff，自动生成 commit message。"""

import argparse
import os
import sys
from pathlib import Path
from typing import Callable, List, Optional

from org_memory.domain import IngestResult
from org_memory.extraction import RuleFactExtractor
from org_memory.ingest import build_commit_guide_ingest_result
from org_memory.store import LocalSQLiteMemoryStore

from .ai_assist import CommitMessageGenerator
from .git_utils import (
    check_git_available,
    execute_add,
    execute_commit,
    execute_push,
    get_remotes,
    get_repo_status,
    get_staged_diff,
    is_git_repo,
)
from .types import format_commit_message, get_commit_types, is_valid_commit_message


PUSH_ALL_REMOTES = "__all__"


class SmartCommit:
    """v2.0 主流程：读取 diff → AI 生成 → 确认提交。

    支持 AI 生成、手动编辑、重新生成三种路径，以及可选的自动暂存、
    推送和组织记忆写入。input_func/output_func 可注入用于测试。
    """

    def __init__(
        self,
        path: str = ".",
        no_ai: bool = False,
        dry_run: bool = False,
        push: bool = False,
        push_target: Optional[str] = None,
        write_memory: bool = False,
        memory_db: Optional[str] = None,
        add_patterns: Optional[List[str]] = None,
        input_func: Callable[[str], str] = input,
        output_func: Callable[[str], None] = print,
        generator: Optional[CommitMessageGenerator] = None,
    ) -> None:
        self.path = path
        self.no_ai = no_ai
        self.dry_run = dry_run
        self.push = push
        self.push_target = push_target
        self.write_memory = write_memory
        self.memory_db = memory_db
        self.add_patterns = add_patterns
        self.input = input_func
        self.output = output_func
        # 允许外部注入 generator，方便单元测试 mock
        self.generator = generator if generator is not None else CommitMessageGenerator()
        # 缓存最后一次 diff 和暂存文件列表，供写入组织记忆时使用
        self._last_diff_context = ""
        self._last_staged_files: List[str] = []

    def run(self) -> int:
        """公开入口，捕获所有异常并转换为退出码。"""
        try:
            return self._run()
        except KeyboardInterrupt:
            self.output("\n已取消提交")
            return 1
        except Exception as exc:
            self.output("错误: {0}".format(exc))
            return 1

    def _run(self) -> int:
        # 1. 检查 Git 环境
        if not check_git_available():
            raise RuntimeError("未检测到 Git，请先安装 Git 2.30+")
        if not is_git_repo(self.path):
            raise RuntimeError("当前目录不是 Git 仓库，请在仓库目录下运行")

        # 2. 获取仓库状态
        status = get_repo_status(self.path)
        self.output("═══════════════════════════════════════════════════════════")
        self.output("                    commit-guide v2.0")
        self.output("═══════════════════════════════════════════════════════════")
        self.output("")
        self.output("📂 当前仓库: {0}".format(status.repo_name))
        self.output("🌿 当前分支: {0}".format(status.branch))
        self.output("")

        # 3. 暂存区为空 → 尝试自动暂存，否则退出
        if not status.has_staged:
            if self.add_patterns:
                if not self._auto_add(self.add_patterns):
                    return 1
                status = get_repo_status(self.path)
                if not status.has_staged:
                    self.output("git add 后暂存区仍为空，没有可提交的变更。")
                    return 1
            else:
                self.output("暂存区为空，请先执行 git add 暂存文件，或使用 --add 自动暂存。")
                return 1

        self.output("暂存区文件 ({0}):".format(len(status.staged)))
        for item in status.staged:
            self.output("  ✓ {0}".format(item))

        # 4. 获取 diff
        diff = get_staged_diff(self.path)
        if not diff.strip():
            self.output("\n暂存区无实际变更内容（diff 为空），无法分析。")
            return 1
        self._last_diff_context = diff
        self._last_staged_files = list(status.staged)

        # 5. 尝试 AI 生成
        message = None
        if not self.no_ai and self.generator.is_available():
            message = self._try_generate(diff, status.staged)

        # 6. 预览与决策
        return self._preview_and_decide(message, status)

    def _auto_add(self, patterns: List[str]) -> bool:
        """执行 git add，dry_run 模式下跳过实际操作。"""
        self.output("⏳ 自动暂存: {0}".format(" ".join(patterns)))
        if self.dry_run:
            self.output("[dry-run] 跳过 git add")
            return True
        ok, detail = execute_add(patterns, self.path)
        if ok:
            self.output("✓ 已暂存")
        else:
            self.output("✗ git add 失败: {0}".format(detail or "未知错误"))
        return ok

    def _try_generate(self, diff: str, staged_files: list) -> Optional[str]:
        """调用 AI 生成 commit message，失败返回 None。"""
        self.output("\n⏳ AI 正在分析 diff 并生成 commit message...")
        result = self.generator.generate(diff, staged_files)
        if result.success:
            return result.message
        self.output("⚠ AI 生成失败: {0}".format(result.reason))
        return None

    def _preview_and_decide(
        self, message: Optional[str], status
    ) -> int:
        """展示生成结果或进入手动编辑，处理用户决策循环。

        选项动态构建：AI 可用时才显示"重新生成"。
        """
        while True:
            self.output("")
            if message:
                self.output("───────────────────────────────────────────────────────────")
                self.output("生成的 commit message:")
                self.output("")
                self.output("  {0}".format(message))
                self.output("")
                self.output("───────────────────────────────────────────────────────────")
            else:
                self.output("（未生成 commit message，请选择手动编辑）")

            options = ["确认提交", "手动编辑"]
            if self.generator.is_available() and not self.no_ai:
                options.append("重新生成")
            options.append("取消")

            for index, label in enumerate(options, start=1):
                self.output("  [{0}] {1}".format(index, label))

            choice = self.input("\n请选择 (1-{0}): ".format(len(options))).strip()
            try:
                index = int(choice)
                label = options[index - 1]
            except (ValueError, IndexError):
                self.output("选择无效，请重新输入")
                continue

            if label == "确认提交":
                if not message:
                    self.output("没有可提交的 message，请先编辑。")
                    continue
                return self._do_commit(message, status)

            if label == "手动编辑":
                message = self._manual_edit(message)
                if message is None:
                    self.output("已取消提交")
                    return 1

            elif label == "重新生成":
                diff = get_staged_diff(self.path)
                self._last_diff_context = diff
                self._last_staged_files = list(status.staged)
                message = self._try_generate(diff, status.staged)

            elif label == "取消":
                self.output("已取消提交")
                return 1

    def _manual_edit(self, base_message: Optional[str] = None) -> Optional[str]:
        """手动编辑模式：有现有 message 时支持追加正文要点，否则走完整重写。

        返回生成的 message 字符串，用户取消则返回 None。
        """
        if base_message:
            edited = self._edit_existing_message(base_message)
            if edited is not None:
                return edited
            return None
        return self._rewrite_message()

    def _edit_existing_message(self, base_message: str) -> Optional[str]:
        """基于已有 commit message 追加正文要点，或选择完整重写。"""
        self.output("\n─── 手动编辑模式 ───\n")
        self.output("当前 message:")
        self.output(base_message)
        self.output("")
        self.output("请选择编辑方式:")
        self.output("  [1] 在当前 message 后追加正文要点")
        self.output("  [2] 完全重写")
        self.output("  [3] 取消编辑")
        while True:
            choice = self.input("请输入序号 (1-3): ").strip()
            if choice == "1":
                return self._append_body_items(base_message)
            if choice == "2":
                return self._rewrite_message()
            if choice == "3":
                return None
            self.output("选择无效，请重新输入")

    def _append_body_items(self, base_message: str) -> Optional[str]:
        """向现有 message 追加正文要点；空行结束输入。"""
        self.output("请输入要追加的正文要点，逐行输入，空行结束。")
        self.output("提示：不用输入 '- '，工具会自动补。")
        additions: List[str] = []
        while True:
            raw = self.input("追加要点: ").strip()
            if not raw:
                break
            additions.append(raw)
        if not additions:
            self.output("未输入追加内容，保留原 message。")
            return base_message
        message = append_commit_body_items(base_message, additions)
        if not is_valid_commit_message(message):
            self.output("追加后的 message 第一行不符合规范，请重新编辑。")
            return None
        self.output("\n预览:")
        self.output(message)
        confirm = self.input("确认使用此 message? [Y/n]: ").strip().lower()
        if confirm in ("", "y", "yes"):
            return message
        return None

    def _rewrite_message(self) -> Optional[str]:
        """完整重写 commit message：复用 v1.0 的 type/scope/描述 交互逻辑。"""
        self.output("\n─── 手动编辑模式 ───\n")

        # 选择 type
        self.output("请选择本次提交类型:")
        commit_types = get_commit_types()
        for index, item in enumerate(commit_types, start=1):
            self.output("  [{0}] {1} - {2}".format(index, item.key, item.description))
        while True:
            raw = self.input("请输入序号 (1-{0}): ".format(len(commit_types))).strip()
            try:
                idx = int(raw)
                type_key = commit_types[idx - 1].key
                break
            except (ValueError, IndexError):
                self.output("选择无效，请重新输入")

        # 输入 scope
        raw = self.input("请输入影响范围（模块名），回车跳过: ").strip()
        scope = raw or None

        # 输入描述
        while True:
            raw = self.input("请输入变更描述（一句话，5-100 字符）: ").strip()
            if len(raw) < 5:
                self.output("描述过短（至少 5 个字符），请重新输入")
                continue
            if len(raw) > 100:
                self.output("描述过长，已截断为 100 字符")
            description = raw[:100]
            break

        message = format_commit_message(type_key, scope, description)
        self.output("\n预览: {0}".format(message))
        confirm = self.input("确认使用此 message? [Y/n]: ").strip().lower()
        if confirm in ("", "y", "yes"):
            return message
        return None

    def _do_commit(self, message: str, status) -> int:
        """执行 git commit，dry_run 模式下只打印不提交。提交成功后可选推送和写入记忆。"""
        if self.dry_run:
            self.output("\n[dry-run] message: {0}".format(message))
            return 0
        result = execute_commit(message, self.path)
        if not result.success:
            self.output("git commit 失败: {0}".format(result.error_message or "unknown"))
            return 2
        self.output("✓ 提交成功: {0}".format(result.sha or "unknown"))
        selected_remote = None

        if self.push:
            remote = normalize_push_target(self.push_target) or self._select_push_remote()
            selected_remote = remote
            if not remote:
                self.output("⚠ 未选择推送目标，请手动执行 git push")
                if self.write_memory:
                    self._write_commit_memory(message, status, result.sha or "unknown", selected_remote)
                return 0
            if remote == PUSH_ALL_REMOTES:
                selected_remote = self._push_all_remotes(status.branch)
            else:
                ok, detail = execute_push(self.path, remote=remote, branch=status.branch)
                if ok:
                    self.output("✓ 推送成功: {0}".format(format_push_target(remote, status.branch)))
                else:
                    self.output("⚠ 推送失败: {0}".format(detail or "未知错误"))
        if self.write_memory:
            self._write_commit_memory(message, status, result.sha or "unknown", selected_remote)
        return 0

    def _push_all_remotes(self, branch: str) -> str:
        """推送到所有 remote，单个 remote 失败不影响其他 remote 继续重试。"""
        remotes = get_remotes(self.path)
        if not remotes:
            self.output("⚠ 未配置 Git remote，请手动添加远端后推送")
            return PUSH_ALL_REMOTES
        pushed: List[str] = []
        failed: List[str] = []
        self.output("\n将推送到所有 Git remote: {0}".format(", ".join(remotes)))
        for remote in remotes:
            ok, detail = execute_push(self.path, remote=remote, branch=branch)
            if ok:
                pushed.append(remote)
                self.output("✓ 推送成功: {0}".format(format_push_target(remote, branch)))
            else:
                failed.append(remote)
                self.output("⚠ 推送失败 {0}: {1}".format(remote, detail or "未知错误"))
        if failed:
            self.output("⚠ 部分 remote 推送失败: {0}".format(", ".join(failed)))
        return ",".join(pushed) if pushed else PUSH_ALL_REMOTES

    def _write_commit_memory(self, message: str, status, commit_sha: str, push_remote: Optional[str]) -> None:
        """将本次提交信息写入 org_memory SQLite 数据库，失败时只打印警告不中断流程。"""
        try:
            store = LocalSQLiteMemoryStore(str(self._resolve_memory_db_path()))
            ingest = build_commit_guide_ingest_result(
                repo_name=status.repo_name,
                branch=status.branch,
                staged_files=self._last_staged_files or list(status.staged),
                diff_context=self._last_diff_context,
                commit_message=message,
                commit_sha=commit_sha,
                actor=self._actor_identity(),
                push_remote=push_remote,
            )
            # 在 ingest 基础上叠加规则提取的 facts 和 relationships
            extraction = RuleFactExtractor().extract(ingest.events)
            combined = IngestResult(
                entities=ingest.entities,
                sources=ingest.sources,
                events=ingest.events,
                facts=ingest.facts + extraction.facts,
                relationships=ingest.relationships + extraction.relationships,
            )
            store.apply_ingest_result(combined)
            store.audit(
                action="commit_guide_ingest",
                target_type="commit",
                target_id=commit_sha,
                actor_id=self._actor_identity(),
                reason="write-memory CLI option",
            )
            self.output("✓ 已写入组织记忆: {0}".format(self._resolve_memory_db_path()))
        except Exception as exc:
            self.output("⚠ 组织记忆写入失败: {0}".format(exc))

    def _resolve_memory_db_path(self) -> Path:
        """解析 org_memory SQLite 文件路径，默认为 data/org_memory.sqlite。"""
        if self.memory_db:
            return Path(self.memory_db).expanduser()
        return Path(__file__).resolve().parents[2] / "data" / "org_memory.sqlite"

    def _actor_identity(self) -> str:
        """从环境变量获取当前操作者标识，用于写入组织记忆的 actor_id。"""
        return os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"

    def _select_push_remote(self) -> Optional[str]:
        """当存在多个 remote 时，交互式让用户选择推送目标；单 remote 时自动选择。"""
        remotes = get_remotes(self.path)
        if not remotes:
            return None
        if len(remotes) == 1:
            return remotes[0]

        self.output("\n检测到多个 Git remote，请选择推送目标:")
        self.output("  [0] 所有")
        for index, remote in enumerate(remotes, start=1):
            self.output("  [{0}] {1}".format(index, remote))
        self.output("  [{0}] 跳过推送".format(len(remotes) + 1))

        while True:
            choice = self.input("请选择推送目标 (0-{0}): ".format(len(remotes) + 1)).strip()
            try:
                index = int(choice)
            except ValueError:
                self.output("选择无效，请重新输入")
                continue
            if index == 0:
                return PUSH_ALL_REMOTES
            if 1 <= index <= len(remotes):
                return remotes[index - 1]
            if index == len(remotes) + 1:
                return None
            self.output("选择无效，请重新输入")


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    """解析 CLI 参数，返回 Namespace 对象。"""
    parser = argparse.ArgumentParser(description="commit-guide v2.0")
    parser.add_argument("--no-ai", action="store_true", help="禁用 AI 生成，直接进入手动编辑")
    parser.add_argument("--path", default=".", help="指定 Git 仓库路径")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，只生成不提交")
    parser.add_argument("--push", action="store_true", help="提交后自动推送")
    parser.add_argument("--push-target", default=None, help="指定推送 remote 名称，如 origin、github、gitea")
    parser.add_argument("--write-memory", action="store_true", help="提交成功后写入 org_memory SQLite 组织记忆")
    parser.add_argument("--memory-db", default=None, help="org_memory SQLite 路径，默认 data/org_memory.sqlite")
    parser.add_argument(
        "--add",
        nargs="*",
        metavar="PATH",
        help="提交前自动 git add，不传路径时默认暂存目标仓库当前目录",
    )
    parser.add_argument("-v", "--version", action="version", version="commit-guide 2.0.0")
    return parser.parse_args(argv)


def resolve_add_patterns(args: argparse.Namespace) -> Optional[List[str]]:
    """解析 --add 参数；不带路径时默认 git add .，路径相对于 --path 指向的仓库。"""
    if args.add is None:
        return None
    if args.add:
        return args.add
    return ["."]


def append_commit_body_items(base_message: str, additions: List[str]) -> str:
    """在 commit message 后追加正文 bullet，保留原 subject 和已有正文。"""
    lines = [line.rstrip() for line in base_message.strip().splitlines()]
    cleaned = []
    for item in additions:
        text = item.strip()
        if not text:
            continue
        if text.startswith("-"):
            text = text[1:].strip()
        if text:
            cleaned.append(text)
    if not cleaned:
        return base_message.strip()
    while lines and not lines[-1].strip():
        lines.pop()
    if len(lines) == 1:
        lines.append("")
    elif lines and lines[-1].strip():
        lines.append("")
    lines.extend("- {0}".format(item) for item in cleaned)
    return "\n".join(lines).strip()


def normalize_push_target(value: Optional[str]) -> Optional[str]:
    """规范化 --push-target，允许 all/*/所有 表示推送全部 remote。"""
    if value is None:
        return None
    text = value.strip()
    if text.lower() in ("all", "*", PUSH_ALL_REMOTES) or text == "所有":
        return PUSH_ALL_REMOTES
    return text or None


def format_push_target(remote: str, branch: str) -> str:
    """格式化推送目标，分支未知时不显示 /unknown。"""
    if branch and branch not in ("HEAD", "unknown"):
        return "{0}/{1}".format(remote, branch)
    return remote


def main(argv: Optional[list] = None) -> int:
    """CLI 入口：解析参数并启动 SmartCommit 主流程。"""
    args = parse_args(argv)
    add_patterns = resolve_add_patterns(args)
    app = SmartCommit(
        path=args.path,
        no_ai=args.no_ai,
        dry_run=args.dry_run,
        push=args.push,
        push_target=args.push_target,
        write_memory=args.write_memory,
        memory_db=args.memory_db,
        add_patterns=add_patterns,
    )
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
