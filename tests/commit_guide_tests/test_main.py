import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from commit_guide.main import SmartCommit


class SmartCommitTest(unittest.TestCase):
    def test_manual_edit_generates_valid_message(self) -> None:
        """模拟完整的手动编辑流程。"""
        inputs = iter([
            "1",                    # 选择 feat
            "auth",                 # scope
            "新增 JWT 登录接口",      # description
            "y",                    # 确认
        ])
        outputs = []
        app = SmartCommit(
            input_func=lambda _prompt: next(inputs),
            output_func=outputs.append,
            no_ai=True,
            dry_run=True,
        )

        message = app._manual_edit()
        self.assertEqual(message, "feat(auth): 新增 JWT 登录接口")

    def test_manual_edit_long_description_truncated(self) -> None:
        """描述过长时截断到 100 字符。"""
        long_desc = "这是一段超过一百个字符的提交描述" * 8
        inputs = iter([
            "2",           # fix
            "",            # no scope
            long_desc,     # excessively long description
            "y",           # confirm
        ])
        outputs = []
        app = SmartCommit(
            input_func=lambda _prompt: next(inputs),
            output_func=outputs.append,
            no_ai=True,
            dry_run=True,
        )

        message = app._manual_edit()
        self.assertTrue(message.startswith("fix: "))
        # description in message = message minus "fix: " = at most 100 chars
        self.assertLessEqual(len(message), 100 + len("fix: "))

    def test_manual_edit_short_description_rejected(self) -> None:
        """描述过短时被拒绝，重新输入后接受。"""
        inputs = iter([
            "3",           # refactor
            "",            # no scope
            "改",          # too short
            "重构用户模块数据访问层",  # valid
            "y",           # confirm
        ])
        outputs = []
        app = SmartCommit(
            input_func=lambda _prompt: next(inputs),
            output_func=outputs.append,
            no_ai=True,
        )

        message = app._manual_edit()
        self.assertEqual(message, "refactor: 重构用户模块数据访问层")
        self.assertIn("过短", "".join(outputs))


if __name__ == "__main__":
    unittest.main()
