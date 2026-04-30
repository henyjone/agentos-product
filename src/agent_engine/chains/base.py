from dataclasses import dataclass, field
from typing import Any, Protocol

from ..schemas import AgentRequest, AgentResponse


@dataclass(frozen=True)
class ChainContext:
    retrieved_context: dict[str, Any] = field(default_factory=dict)


class AgentChain(Protocol):
    """Protocol for hand-written MVP chains.

    Concrete chains should keep orchestration out of AgentOrchestrator and own
    their prompt, model call, parsing, and safety handoff for one scenario.
    """

    name: str

    def run(self, request: AgentRequest, context: ChainContext) -> AgentResponse:
        """Return a structured response for one agent scenario."""
