from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ModelRequest:
    prompt: str
    system: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelResponse:
    text: str
    raw: dict[str, Any] = field(default_factory=dict)


class ModelClient(Protocol):
    """Model provider abstraction for hand-written chains."""

    def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate model output for a chain-owned prompt."""
