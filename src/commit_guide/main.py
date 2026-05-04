"""commit-guide v2.0 —— AI 读取 diff，自动生成 commit message。"""

import argparse
import sys
from typing import Callable, Optional

from .ai_assist import CommitMessageGenerator
from .git_utils import (
    check_git_available,
    execute_commit,
    execute_push,
    get_repo_status,
    get_staged_diff,
    is_git_repo,
)
from .types import format_commit_message, get_commit_types, is_valid_commit_message


class SmartCommit:
    """v2.0 主流程：读取 diff → AI 生成 → 确认提交。"""

    def __init__(
        self,
        path: str = ".",
        no_ai: bool = False,
        dry_run: bool = False,
        push: bool = False,
        input_func: Callable[[str], str] = input,
        output_func: Callable[[str], None] = print,
        generator: Optional[CommitMessageGenerator] = None,
    ) -> None:
        self.path = path
        self.no_ai = no_ai
        self.dry_run = dry_run
        self.push = push
        self.input = input_func
        self.output = output_func
        self.generator = generator if generator is not None else CommitMessageGenerator()

    def run(self) -> int:
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

        # 3. 暂存区为空 → 直接退出
        if not status.has_staged:
            self.output("暂存区为空，请先执行 git add 暂存文件。")
            return 1

        self.output("暂存区文件 ({0}):".format(len(status.staged)))
        for item in status.staged:
            self.output("  ✓ {0}".format(item))

        # 4. 获取 diff
        diff = get_staged_diff(self.path)
        if not diff.strip():
            self.output("\n暂存区无实际变更内容（diff 为空），无法分析。")
            return 1

        # 5. 尝试 AI 生成
        message = None
        if not self.no_ai and self.generator.is_available():
            message = self._try_generate(diff, status.staged)

        # 6. 预览与决策
        return self._preview_and_decide(message, status)

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
        """展示生成结果或进入手动编辑，处理用户决策。"""
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
                return self._do_commit(message)

            if label == "手动编辑":
                message = self._manual_edit()
                if message is None:
                    self.output("已取消提交")
                    return 1

            elif label == "重新生成":
                diff = get_staged_diff(self.path)
                message = self._try_generate(diff, status.staged)

            elif label == "取消":
                self.output("已取消提交")
                return 1

    def _manual_edit(self) -> Optional[str]:
        """手动编辑模式：复用 v1.0 的 type/scope/描述 交互逻辑。

        返回生成的 message 字符串，用户取消则返回 None。
        """
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

    def _do_commit(self, message: str) -> int:
        if self.dry_run:
            self.output("\n[dry-run] message: {0}".format(message))
            return 0
        result = execute_commit(message, self.path)
        if not result.success:
            self.output("git commit 失败: {0}".format(result.error_message or "unknown"))
            return 2
        self.output("✓ 提交成功: {0}".format(result.sha or "unknown"))

        if self.push:
            if execute_push(self.path):
                self.output("✓ 推送成功")
            else:
                self.output("⚠ 推送失败，请手动执行 git push")
        return 0


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="commit-guide v2.0")
    parser.add_argument("--no-ai", action="store_true", help="禁用 AI 生成，直接进入手动编辑")
    parser.add_argument("--path", default=".", help="指定 Git 仓库路径")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，只生成不提交")
    parser.add_argument("--push", action="store_true", help="提交后自动推送")
    parser.add_argument("-v", "--version", action="version", version="commit-guide 2.0.0")
    return parser.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = parse_args(argv)
    app = SmartCommit(
        path=args.path,
        no_ai=args.no_ai,
        dry_run=args.dry_run,
        push=args.push,
    )
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
