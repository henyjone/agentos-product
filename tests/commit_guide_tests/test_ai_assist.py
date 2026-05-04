import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from commit_guide.ai_assist import CommitMessageGenerator
from commit_guide.types import is_valid_commit_message


class CommitMessageGeneratorTest(unittest.TestCase):
    def test_extracts_multiline_commit_message(self) -> None:
        raw = """说明如下：

feat(commit-guide): 支持基于暂存区 diff 生成提交说明

- 新增 AI 分析暂存区 diff 的提交信息生成流程
- 补充配置读取和 Git 状态检测逻辑
"""

        message = CommitMessageGenerator._extract_message(raw)

        self.assertIsNotNone(message)
        self.assertTrue(is_valid_commit_message(message))
        self.assertIn("- 新增 AI 分析", message)


if __name__ == "__main__":
    unittest.main()
