"""内存存储实现 —— 基于字典的 MemoryStore，主要用于测试和轻量场景。"""

from datetime import date, datetime, time, timezone
from typing import Dict, List, Optional

from ..domain import Entity, Fact, IngestResult, MemoryQuery, RawEvent, Relationship, Source
from ..scope import AccessContext, PermissionPolicy


class InMemoryMemoryStore:
    """基于内存字典的 MemoryStore 实现，数据不持久化，进程退出后丢失。"""

    def __init__(self, permission_policy: Optional[PermissionPolicy] = None):
        self.entities: Dict[str, Entity] = {}
        self.sources: Dict[str, Source] = {}
        self.events: Dict[str, RawEvent] = {}
        self.facts: Dict[str, Fact] = {}
        self.relationships: Dict[str, Relationship] = {}
        self.audit_events: List[Dict] = []
        self.permission_policy = permission_policy or PermissionPolicy()

    def upsert_entity(self, entity: Entity) -> None:
        self.entities[entity.id] = entity

    def upsert_source(self, source: Source) -> None:
        self.sources[source.id] = source

    def append_event(self, event: RawEvent) -> None:
        self.events[event.id] = event

    def upsert_fact(self, fact: Fact) -> None:
        self.facts[fact.id] = fact

    def upsert_relationship(self, relationship: Relationship) -> None:
        self.relationships[relationship.id] = relationship

    def apply_ingest_result(self, result: IngestResult) -> None:
        """批量写入 IngestResult 中的所有领域对象。"""
        for entity in result.entities:
            self.upsert_entity(entity)
        for source in result.sources:
            self.upsert_source(source)
        for event in result.events:
            self.append_event(event)
        for fact in result.facts:
            self.upsert_fact(fact)
        for relationship in result.relationships:
            self.upsert_relationship(relationship)

    def search_facts(self, query: MemoryQuery) -> List[Fact]:
        """按查询条件检索事实，应用权限过滤后按时间倒序返回。"""
        context = AccessContext(
            user_id=query.user_id,
            role=query.role,
            team_ids=tuple(query.team_ids),
            project_ids=tuple(query.project_ids),
            break_glass=query.break_glass,
            reason=query.reason,
        )
        results: List[Fact] = []
        for fact in self.facts.values():
            if fact.status != "active":
                continue
            if query.project_ids and fact.project_id not in query.project_ids:
                continue
            if query.person_ids and fact.subject_entity_id not in query.person_ids:
                continue
            if query.fact_types and fact.fact_type not in query.fact_types:
                continue
            if query.source_types and not _matches_source_types(fact.source_ids, self.sources, query.source_types):
                continue
            if query.scopes and fact.scope not in query.scopes:
                continue
            if not _in_time_window(
                fact.valid_from or fact.updated_at or fact.created_at,
                query.time_from,
                query.time_to,
            ):
                continue
            if not self.permission_policy.can_read(
                context=context,
                scope=fact.scope,
                sensitivity=fact.sensitivity,
                owner_id=fact.subject_entity_id,
                project_id=fact.project_id,
                team_id=fact.metadata.get("team_id"),
            ):
                continue
            results.append(fact)
        results.sort(key=lambda item: item.updated_at or item.created_at, reverse=True)
        return results[: max(0, query.limit)]

    def list_events(self, query: MemoryQuery) -> List[RawEvent]:
        """按查询条件列出原始事件，应用权限过滤后按发生时间倒序返回。"""
        context = AccessContext(
            user_id=query.user_id,
            role=query.role,
            team_ids=tuple(query.team_ids),
            project_ids=tuple(query.project_ids),
            break_glass=query.break_glass,
            reason=query.reason,
        )
        results: List[RawEvent] = []
        for event in self.events.values():
            if query.project_ids and event.project_id not in query.project_ids:
                continue
            if query.person_ids and event.actor_id not in query.person_ids:
                continue
            if query.scopes and event.scope not in query.scopes:
                continue
            if not _in_time_window(event.occurred_at, query.time_from, query.time_to):
                continue
            if not self.permission_policy.can_read(
                context=context,
                scope=event.scope,
                sensitivity=event.sensitivity,
                owner_id=event.actor_id,
                project_id=event.project_id,
                team_id=event.payload.get("team_id"),
            ):
                continue
            results.append(event)
        results.sort(key=lambda item: item.occurred_at, reverse=True)
        return results[: max(0, query.limit)]

    def get_source(self, source_id: str) -> Optional[Source]:
        return self.sources.get(source_id)

    def audit(self, action: str, target_type: str, target_id: str, actor_id: str, reason: str) -> None:
        """记录审计事件到内存列表（不持久化）。"""
        self.audit_events.append(
            {
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
                "actor_id": actor_id,
                "reason": reason,
            }
        )


def _in_time_window(value: str, time_from: Optional[str], time_to: Optional[str]) -> bool:
    """判断时间字符串是否在 [time_from, time_to] 范围内，支持小时级 ISO 时间比较。"""
    if not value:
        return True
    current = _parse_time(value)
    start = _parse_time(time_from)
    end = _parse_time(time_to, end_of_day=True)
    if current is None:
        return True
    if start and current < start:
        return False
    if end and current > end:
        return False
    return True


def _parse_time(value: Optional[str], end_of_day: bool = False) -> Optional[datetime]:
    """解析 ISO 日期/时间；date-only 的上界按当天结束处理，保持旧查询语义。"""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if len(text) <= 10:
            parsed_date = date.fromisoformat(text[:10])
            parsed = datetime.combine(parsed_date, time.max if end_of_day else time.min)
        else:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _matches_source_types(source_ids: List[str], sources: Dict[str, Source], source_types: List[str]) -> bool:
    """判断 source_ids 中是否有任意一个来源的 source_type 在 source_types 列表中。"""
    for source_id in source_ids:
        source = sources.get(source_id)
        if source and source.source_type in source_types:
            return True
    return False
