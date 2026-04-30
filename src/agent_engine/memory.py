from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class MemoryScope(str, Enum):
    PERSONAL = "personal"
    TEAM = "team"
    ORG = "org"
    RESTRICTED = "restricted"


@dataclass(frozen=True)
class MemoryItem:
    id: str
    owner_id: str
    scope: MemoryScope
    section: str
    content: str
    source: str
    source_id: str = ""
    sensitivity: str = "internal"
    created_at: str = ""
    updated_at: str = ""
    version: int = 1


class MemoryClient(Protocol):
    """Storage-agnostic memory interface consumed by agent_engine."""

    def search(self, query: str, *, user_id: str, scope: MemoryScope) -> list[MemoryItem]:
        """Return authorized memory items for the current agent request."""
