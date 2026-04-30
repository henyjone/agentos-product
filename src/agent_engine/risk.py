from typing import Optional

from .schemas import AgentAction, AgentRequest


class RiskClassifier:
    """Classifies whether a request implies a high-risk action."""

    _high_risk_terms = {
        "send_message": ("发送", "发消息", "通知客户", "同步给客户"),
        "send_email": ("发邮件", "邮件给"),
        "create_task": ("创建任务", "建任务", "新建任务"),
        "update_project_state": ("修改状态", "更新项目状态", "关闭项目"),
        "access_sensitive_memory": ("敏感记忆", "私人记忆", "restricted", "private"),
    }

    def classify(self, request: AgentRequest) -> Optional[AgentAction]:
        for action_type, terms in self._high_risk_terms.items():
            if any(term in request.message for term in terms):
                return AgentAction(
                    action_type=action_type,
                    title=self._title_for(action_type),
                    risk_level="high",
                    reason="该请求可能产生外部影响、修改正式系统状态或访问敏感内容，需要进入审批。",
                    payload={"original_message": request.message},
                )
        return None

    @staticmethod
    def _title_for(action_type: str) -> str:
        titles = {
            "send_message": "发送消息",
            "send_email": "发送邮件",
            "create_task": "创建任务",
            "update_project_state": "修改项目状态",
            "access_sensitive_memory": "访问敏感记忆",
        }
        return titles.get(action_type, "高风险动作")
