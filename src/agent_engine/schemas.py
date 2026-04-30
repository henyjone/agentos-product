from dataclasses import dataclass, field
from typing import Any, Optional

from .modes import AgentMode


@dataclass(frozen=True)
class SourceReference:
    source_id: str
    source_type: str
    title: str
    url: Optional[str] = None
    sensitivity: str = "internal"


@dataclass(frozen=True)
class AgentRequest:
    user_id: str
    role: str
    message: str
    entrypoint: str = "chat"
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentAction:
    action_type: str
    title: str
    risk_level: str
    reason: str
    requires_approval: bool = True
    payload: dict[str, Any] = field(default_factory=dict)
    sources: list[SourceReference] = field(default_factory=list)


@dataclass(frozen=True)
class Uncertainty:
    level: str = "low"
    reason: str = ""


@dataclass(frozen=True)
class SafetyState:
    contains_sensitive_data: bool = False
    policy_warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Answer:
    summary: str
    facts: list[str] = field(default_factory=list)
    inferences: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AgentResponse:
    mode: AgentMode
    answer: Answer
    sources: list[SourceReference] = field(default_factory=list)
    actions: list[AgentAction] = field(default_factory=list)
    requires_confirmation: bool = False
    uncertainty: Uncertainty = field(default_factory=Uncertainty)
    safety: SafetyState = field(default_factory=SafetyState)
