import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from commit_guide import git_utils


def completed(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(
        args=["git"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class GitUtilsTest(unittest.TestCase):
    @patch("commit_guide.git_utils.subprocess.run")
    def test_check_git_available_success(self, run_mock) -> None:
        run_mock.return_value = completed(stdout="git version 2.40")

        self.assertTrue(git_utils.check_git_available())

    @patch("commit_guide.git_utils.subprocess.run")
    def test_get_repo_status(self, run_mock) -> None:
        run_mock.side_effect = [
            completed(stdout=".git"),
            completed(stdout="main\n"),
            completed(stdout="src/app.py\n"),
            completed(stdout="README.md\n"),
            completed(stdout="new.txt\n"),
        ]

        status = git_utils.get_repo_status(".")

        self.assertEqual(status.branch, "main")
        self.assertEqual(status.staged, ["src/app.py"])
        self.assertEqual(status.unstaged, ["README.md"])
        self.assertEqual(status.untracked, ["new.txt"])

    @patch("commit_guide.git_utils.subprocess.run")
    def test_execute_commit_failure(self, run_mock) -> None:
        run_mock.return_value = completed(stderr="nothing to commit", returncode=1)

        result = git_utils.execute_commit("feat: 新增提交说明")

        self.assertFalse(result.success)
        self.assertIn("nothing", result.error_message)

    @patch("commit_guide.git_utils.subprocess.run")
    def test_get_staged_diff_prioritizes_code_snippets(self, run_mock) -> None:
        doc_diff = "diff --git a/docs/guide.md b/docs/guide.md\n" + ("+文档\n" * 200)
        code_diff = (
            "diff --git a/src/commit_guide/main.py b/src/commit_guide/main.py\n"
            "+class SmartCommit:\n"
            "+    pass\n"
        )
        run_mock.side_effect = [
            completed(stdout="docs/guide.md\nsrc/commit_guide/main.py\n"),
            completed(stdout=" docs/guide.md | 200 +\n src/commit_guide/main.py | 2 +\n"),
            completed(stdout="200\t0\tdocs/guide.md\n2\t0\tsrc/commit_guide/main.py\n"),
            completed(stdout=code_diff),
            completed(stdout=doc_diff),
        ]

        context = git_utils.get_staged_diff(max_bytes=2000)

        self.assertIn("## Staged files", context)
        self.assertIn("## Change stat", context)
        self.assertLess(
            context.index("### src/commit_guide/main.py"),
            context.index("### docs/guide.md"),
        )


if __name__ == "__main__":
    unittest.main()
