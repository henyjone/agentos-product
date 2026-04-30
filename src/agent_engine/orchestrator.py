from typing import Optional

from .risk import RiskClassifier
from .router import ModeRouter
from .schemas import AgentRequest, AgentResponse, Answer, Uncertainty


class AgentOrchestrator:
    """Minimal orchestration facade for the first Dev2 milestone."""

    def __init__(
        self,
        router: Optional[ModeRouter] = None,
        risk_classifier: Optional[RiskClassifier] = None,
    ) -> None:
        self._router = router or ModeRouter()
        self._risk_classifier = risk_classifier or RiskClassifier()

    def handle(self, request: AgentRequest) -> AgentResponse:
        mode = self._router.route(request)
        action = self._risk_classifier.classify(request)
        actions = [action] if action else []

        return AgentResponse(
            mode=mode,
            answer=Answer(
                summary="Agent engine MVP 已完成模式识别，后续由具体 chain 生成正式回答。"
            ),
            actions=actions,
            requires_confirmation=bool(actions),
            uncertainty=Uncertainty(
                level="medium",
                reason="当前为规则路由和风险识别骨架，尚未接入 Dev4 上下文与模型生成。",
            ),
        )
