from typing import Optional

from .modes import AgentMode
from .schemas import AgentRequest


class ModeRouter:
    """Rule-based first pass router for Dev2 MVP.

    The production router can later combine these rules with model-based
    classification, but deterministic rules keep early behavior testable.
    """

    _execution_terms = ("发送", "发消息", "发邮件", "创建任务", "修改状态", "同步到")
    _management_terms = ("公司", "组织", "管理层", "最大风险", "组织风险")
    _team_terms = ("项目", "风险", "阻塞", "依赖", "周会", "进展")
    _knowledge_terms = ("查", "为什么", "上次", "历史", "出处", "记录")
    _cowork_terms = ("陪我想", "一起想", "反驳我", "方案", "沟通准备")
    _governance_terms = ("权限", "审计", "敏感", "访问记录", "越权")
    _entry_point_modes = {
        "personal_brief": AgentMode.PERSONAL,
        "cowork": AgentMode.COWORK,
        "projects": AgentMode.TEAM,
        "dashboard": AgentMode.MANAGEMENT,
        "knowledge": AgentMode.KNOWLEDGE,
        "approvals": AgentMode.GOVERNANCE,
        "audit": AgentMode.GOVERNANCE,
        "admin": AgentMode.GOVERNANCE,
    }

    def route(self, request: AgentRequest) -> AgentMode:
        text = request.message.strip()
        hinted_mode = self._mode_from_hint(request)

        if self._contains_any(text, self._execution_terms):
            return AgentMode.EXECUTION
        if self._contains_any(text, self._governance_terms):
            return AgentMode.GOVERNANCE
        if hinted_mode is not None:
            return hinted_mode
        if self._contains_any(text, self._cowork_terms):
            return AgentMode.COWORK
        if self._contains_any(text, self._management_terms):
            return AgentMode.MANAGEMENT
        if self._contains_any(text, self._knowledge_terms):
            return AgentMode.KNOWLEDGE
        if self._contains_any(text, self._team_terms):
            return AgentMode.TEAM
        return AgentMode.PERSONAL

    @staticmethod
    def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
        return any(term in text for term in terms)

    def _mode_from_hint(self, request: AgentRequest) -> Optional[AgentMode]:
        mode_hint = request.context_hint.get("mode_hint")
        if mode_hint:
            try:
                return AgentMode(mode_hint)
            except ValueError:
                pass
        return self._entry_point_modes.get(request.entry_point)
