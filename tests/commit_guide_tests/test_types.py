import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from commit_guide.types import (
    format_commit_message,
    get_commit_types,
    is_valid_commit_message,
    is_valid_type,
)


class CommitTypesTest(unittest.TestCase):
    def test_get_commit_types_returns_all_types(self) -> None:
        self.assertEqual(len(get_commit_types()), 8)

    def test_format_commit_message_with_scope(self) -> None:
        self.assertEqual(
            format_commit_message("feat", "auth", "新增 JWT 登录接口"),
            "feat(auth): 新增 JWT 登录接口",
        )

    def test_format_commit_message_without_scope(self) -> None:
        self.assertEqual(
            format_commit_message("fix", "", "修复分页错误"),
            "fix: 修复分页错误",
        )

    def test_validates_type_and_message(self) -> None:
        self.assertTrue(is_valid_type("feat"))
        self.assertFalse(is_valid_type("feature"))
        self.assertTrue(is_valid_commit_message("docs: 更新接口文档说明"))
        self.assertFalse(is_valid_commit_message("feature: 更新接口文档说明"))


if __name__ == "__main__":
    unittest.main()

