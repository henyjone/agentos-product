import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from agent_engine import AgentMode, AgentRequest, ModeRouter


class ModeRouterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.router = ModeRouter()

    def test_routes_execution_before_knowledge(self) -> None:
        request = AgentRequest(
            user_id="u1",
            role="manager",
            message="帮我发消息给客户说明延期原因",
        )

        self.assertEqual(self.router.route(request), AgentMode.EXECUTION)

    def test_routes_management_question(self) -> None:
        request = AgentRequest(
            user_id="u1",
            role="executive",
            message="公司今天最大风险是什么",
        )

        self.assertEqual(self.router.route(request), AgentMode.MANAGEMENT)

    def test_defaults_to_personal(self) -> None:
        request = AgentRequest(user_id="u1", role="employee", message="今天我该做什么")

        self.assertEqual(self.router.route(request), AgentMode.PERSONAL)


if __name__ == "__main__":
    unittest.main()

