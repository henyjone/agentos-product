"""访问控制模块 —— 定义角色权限规则和权限策略，控制组织记忆的读取范围。"""

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

from .domain import (
    SCOPE_ORG,
    SCOPE_PERSONAL,
    SCOPE_RESTRICTED,
    SCOPE_TEAM,
    SENSITIVITY_INTERNAL,
    SENSITIVITY_PRIVATE,
    SENSITIVITY_PUBLIC,
    SENSITIVITY_RESTRICTED,
)


@dataclass(frozen=True)
class AccessContext:
    """查询时的访问上下文，描述"谁在以什么身份访问"。"""

    user_id: str
    role: str = "employee"
    team_ids: Tuple[str, ...] = ()      # 用户所属团队 ID 列表
    project_ids: Tuple[str, ...] = ()   # 用户有权访问的项目 ID 列表
    break_glass: bool = False           # 是否启用紧急访问（需配合 reason）
    reason: str = ""                    # 紧急访问原因，break_glass=True 时必填


@dataclass(frozen=True)
class AccessRule:
    """单个角色的访问权限规则。"""

    role: str
    readable_scopes: Tuple[str, ...]        # 该角色可读的作用域列表
    readable_sensitivities: Tuple[str, ...] # 该角色可读的敏感度列表
    personal_access: str = "own_only"       # 个人数据访问策略：own_only / any
    can_break_glass: bool = False           # 是否允许紧急访问
    description: str = ""


# 默认角色权限规则集，按最小权限原则设计
DEFAULT_ACCESS_RULES = (
    AccessRule(
        role="employee",
        readable_scopes=(SCOPE_PERSONAL, SCOPE_TEAM, SCOPE_ORG),
        readable_sensitivities=(SENSITIVITY_PUBLIC, SENSITIVITY_INTERNAL, SENSITIVITY_PRIVATE),
        personal_access="own_only",
        description="Employee can read own personal memory plus authorized team/org data.",
    ),
    AccessRule(
        role="team_lead",
        readable_scopes=(SCOPE_PERSONAL, SCOPE_TEAM, SCOPE_ORG),
        readable_sensitivities=(SENSITIVITY_PUBLIC, SENSITIVITY_INTERNAL, SENSITIVITY_PRIVATE),
        personal_access="own_only",
        description="Team lead can read authorized team/org data and own personal memory.",
    ),
    AccessRule(
        role="manager",
        readable_scopes=(SCOPE_PERSONAL, SCOPE_TEAM, SCOPE_ORG),
        readable_sensitivities=(SENSITIVITY_PUBLIC, SENSITIVITY_INTERNAL, SENSITIVITY_PRIVATE),
        personal_access="own_only",
        description="Manager can read authorized team/org facts, not private personal memory by default.",
    ),
    AccessRule(
        role="admin",
        readable_scopes=(SCOPE_PERSONAL, SCOPE_TEAM, SCOPE_ORG, SCOPE_RESTRICTED),
        readable_sensitivities=(
            SENSITIVITY_PUBLIC,
            SENSITIVITY_INTERNAL,
            SENSITIVITY_PRIVATE,
            SENSITIVITY_RESTRICTED,
        ),
        personal_access="own_only",
        can_break_glass=True,
        description="Admin can use audited break-glass access.",
    ),
    AccessRule(
        role="security",
        readable_scopes=(SCOPE_PERSONAL, SCOPE_TEAM, SCOPE_ORG, SCOPE_RESTRICTED),
        readable_sensitivities=(
            SENSITIVITY_PUBLIC,
            SENSITIVITY_INTERNAL,
            SENSITIVITY_PRIVATE,
            SENSITIVITY_RESTRICTED,
        ),
        personal_access="own_only",
        can_break_glass=True,
        description="Security can use audited break-glass access.",
    ),
)


class PermissionPolicy:
    """权限策略引擎，根据角色规则判断是否允许读取特定数据。"""

    def __init__(self, rules: Iterable[AccessRule] = DEFAULT_ACCESS_RULES):
        # 以 role 为 key 建立查找字典，未知角色降级为 employee 规则
        self._rules = {rule.role: rule for rule in rules}

    def rule_for(self, role: str) -> AccessRule:
        """获取指定角色的权限规则，未知角色返回 employee 规则。"""
        return self._rules.get(role, self._rules["employee"])

    def can_read(
        self,
        context: AccessContext,
        scope: str,
        sensitivity: str,
        owner_id: Optional[str] = None,
        project_id: Optional[str] = None,
        team_id: Optional[str] = None,
    ) -> bool:
        """判断给定访问上下文是否有权读取指定作用域和敏感度的数据。

        判断顺序：
        1. 作用域和敏感度必须在角色允许范围内
        2. restricted 数据需要 break_glass + reason
        3. personal/private 数据只允许本人或 break_glass 访问
        4. 项目/团队隔离：有项目/团队限制时需匹配
        """
        rule = self.rule_for(context.role)
        if scope not in rule.readable_scopes:
            return False
        if sensitivity not in rule.readable_sensitivities:
            return False
        # restricted 级别需要显式的 break_glass 授权
        if scope == SCOPE_RESTRICTED or sensitivity == SENSITIVITY_RESTRICTED:
            return bool(rule.can_break_glass and context.break_glass and context.reason.strip())
        # personal/private 数据：只允许本人或 break_glass 访问
        if scope == SCOPE_PERSONAL or sensitivity == SENSITIVITY_PRIVATE:
            if rule.personal_access == "any":
                return True
            if rule.personal_access == "own_only" and owner_id == context.user_id:
                return True
            return bool(rule.can_break_glass and context.break_glass and context.reason.strip())
        # 项目隔离：context 指定了项目范围时，数据必须属于其中一个项目
        if project_id and context.project_ids and project_id not in context.project_ids:
            return False
        # 团队隔离：context 指定了团队范围时，数据必须属于其中一个团队
        if team_id and context.team_ids and team_id not in context.team_ids:
            return False
        return True

    def filter_readable(self, context: AccessContext, items: Iterable) -> List:
        """从 items 中过滤出当前 context 有权读取的条目。"""
        readable = []
        for item in items:
            if self.can_read(
                context=context,
                scope=getattr(item, "scope", SCOPE_TEAM),
                sensitivity=getattr(item, "sensitivity", SENSITIVITY_INTERNAL),
                owner_id=getattr(item, "subject_entity_id", None),
                project_id=getattr(item, "project_id", None),
                team_id=getattr(item, "team_id", None) or getattr(item, "metadata", {}).get("team_id"),
            ):
                readable.append(item)
        return readable
