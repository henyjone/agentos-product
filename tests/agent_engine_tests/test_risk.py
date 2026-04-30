import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from agent_engine import AgentOrchestrator, AgentRequest, RiskClassifier


class RiskClassifierTest(unittest.TestCase):
    def test_generates_approval_action_for_message(self) -> None:
        request = AgentRequest(
            user_id="u1",
            role="manager",
            message="帮我发消息给客户同步项目状态",
        )

        action = RiskClassifier().classify(request)

        self.assertIsNotNone(action)
        self.assertEqual(action.action_type, "send_message")
        self.assertTrue(action.requires_approval)

    def test_orchestrator_marks_confirmation_required(self) -> None:
        request = AgentRequest(
            user_id="u1",
            role="manager",
            message="帮我创建任务跟进支付风险",
        )

        response = AgentOrchestrator().handle(request)

        self.assertTrue(response.requires_confirmation)
        self.assertEqual(response.actions[0].action_type, "create_task")


if __name__ == "__main__":
    unittest.main()

