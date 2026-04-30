from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class MemoryItem:
    id: str
    owner_id: str
    scope: str
    section: str
    content: str
    source: str
    sensitivity: str = "internal"


class MemoryClient(Protocol):
    """Storage-agnostic memory interface consumed by agent_engine."""

    def search(self, query: str, *, user_id: str, scope: str) -> list[MemoryItem]:
        """Return authorized memory items for the current agent request."""

