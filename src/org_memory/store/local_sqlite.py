"""SQLite 持久化存储实现 —— 将所有领域对象序列化为 JSON 存入 SQLite，支持生产环境使用。"""

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Type, TypeVar

from ..domain import Entity, Fact, IngestResult, MemoryQuery, RawEvent, Relationship, Source
from ..scope import AccessContext, PermissionPolicy
from ..time_utils import utc_now_iso
from .utils import apply_ingest_result


T = TypeVar("T")


class LocalSQLiteMemoryStore:
    """基于 SQLite 的 MemoryStore 实现，每张表使用 (id, data_json, updated_at) 三列结构。

    所有领域对象通过 dataclasses.asdict 序列化为 JSON 存储，读取时反序列化还原。
    数据库文件不存在时自动创建，父目录也会自动创建。
    """

    def __init__(self, db_path: str, permission_policy: Optional[PermissionPolicy] = None):
        self.db_path = str(db_path)
        # 确保数据库文件的父目录存在
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.permission_policy = permission_policy or PermissionPolicy()
        self._init_schema()

    def upsert_entity(self, entity: Entity) -> None:
        self._upsert("entities", entity.id, entity)

    def upsert_source(self, source: Source) -> None:
        self._upsert("sources", source.id, source)

    def append_event(self, event: RawEvent) -> None:
        self._upsert("raw_events", event.id, event)

    def upsert_fact(self, fact: Fact) -> None:
        self._upsert("facts", fact.id, fact)

    def upsert_relationship(self, relationship: Relationship) -> None:
        self._upsert("relationships", relationship.id, relationship)

    def apply_ingest_result(self, result: IngestResult) -> None:
        apply_ingest_result(self, result)

    def search_facts(self, query: MemoryQuery) -> List[Fact]:
        """从 SQLite 加载所有事实，在内存中应用过滤和权限校验后返回。"""
        context = AccessContext(
            user_id=query.user_id,
            role=query.role,
            project_ids=tuple(query.project_ids),
            break_glass=query.break_glass,
            reason=query.reason,
        )
        # 预加载 sources 用于 source_type 过滤
        sources = {source.id: source for source in self._load_all("sources", Source)}
        results: List[Fact] = []
        for fact in self._load_all("facts", Fact):
            if fact.status != "active":
                continue
            if query.project_ids and fact.project_id not in query.project_ids:
                continue
            if query.person_ids and fact.subject_entity_id not in query.person_ids:
                continue
            if query.fact_types and fact.fact_type not in query.fact_types:
                continue
            if query.source_types and not _matches_source_types(fact.source_ids, sources, query.source_types):
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
            ):
                continue
            results.append(fact)
        results.sort(key=lambda item: item.updated_at or item.created_at, reverse=True)
        return results[: max(0, query.limit)]

    def list_events(self, query: MemoryQuery) -> List[RawEvent]:
        """从 SQLite 加载所有事件，在内存中应用过滤和权限校验后返回。"""
        context = AccessContext(
            user_id=query.user_id,
            role=query.role,
            project_ids=tuple(query.project_ids),
            break_glass=query.break_glass,
            reason=query.reason,
        )
        results: List[RawEvent] = []
        for event in self._load_all("raw_events", RawEvent):
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
            ):
                continue
            results.append(event)
        results.sort(key=lambda item: item.occurred_at, reverse=True)
        return results[: max(0, query.limit)]

    def get_source(self, source_id: str) -> Optional[Source]:
        return self._get("sources", source_id, Source)

    def audit(self, action: str, target_type: str, target_id: str, actor_id: str, reason: str) -> None:
        """将审计事件写入 audit_events 表，row_id 包含时间戳保证唯一性。"""
        payload = {
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "actor_id": actor_id,
            "reason": reason,
            "created_at": utc_now_iso(),
        }
        row_id = "{0}:{1}:{2}".format(action, target_id, payload["created_at"])
        self._upsert_json("audit_events", row_id, payload)

    def _init_schema(self) -> None:
        """初始化数据库表结构，所有表使用统一的三列 schema：id / data_json / updated_at。"""
        with self._connect() as conn:
            for table in (
                "entities",
                "sources",
                "raw_events",
                "facts",
                "relationships",
                "audit_events",
            ):
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS {0} (
                        id TEXT PRIMARY KEY,
                        data_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """.format(table)
                )

    def _connect(self) -> sqlite3.Connection:
        """创建并返回 SQLite 连接，每次操作独立连接以避免线程问题。"""
        return sqlite3.connect(self.db_path)

    def _upsert(self, table: str, row_id: str, item) -> None:
        """将 dataclass 实例序列化为 JSON 后 upsert 到指定表。"""
        self._upsert_json(table, row_id, asdict(item))

    def _upsert_json(self, table: str, row_id: str, data: Dict) -> None:
        """将字典序列化为 JSON 后 INSERT OR REPLACE 到指定表。"""
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO {0} (id, data_json, updated_at) VALUES (?, ?, ?)".format(table),
                (row_id, json.dumps(data, ensure_ascii=False, sort_keys=True), utc_now_iso()),
            )

    def _get(self, table: str, row_id: str, cls: Type[T]) -> Optional[T]:
        """按 ID 从指定表读取单条记录并反序列化为指定类型。"""
        with self._connect() as conn:
            row = conn.execute("SELECT data_json FROM {0} WHERE id = ?".format(table), (row_id,)).fetchone()
        if not row:
            return None
        return cls(**json.loads(row[0]))

    def _load_all(self, table: str, cls: Type[T]) -> List[T]:
        """加载指定表的所有记录并反序列化为指定类型列表。"""
        with self._connect() as conn:
            rows = conn.execute("SELECT data_json FROM {0}".format(table)).fetchall()
        return [cls(**json.loads(row[0])) for row in rows]


def _in_time_window(value: str, time_from: Optional[str], time_to: Optional[str]) -> bool:
    """判断时间字符串是否在 [time_from, time_to] 范围内，只比较日期部分（前 10 位）。"""
    if not value:
        return True
    current = value[:10] if len(value) >= 10 else value
    if time_from and current < time_from[:10]:
        return False
    if time_to and current > time_to[:10]:
        return False
    return True


def _matches_source_types(source_ids: List[str], sources: Dict[str, Source], source_types: List[str]) -> bool:
    """判断 source_ids 中是否有任意一个来源的 source_type 在 source_types 列表中。"""
    for source_id in source_ids:
        source = sources.get(source_id)
        if source and source.source_type in source_types:
            return True
    return False
