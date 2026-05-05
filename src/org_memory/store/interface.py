"""存储层接口定义 —— 使用 Protocol 定义 MemoryStore 的标准契约，支持多种后端实现。"""

from typing import Optional, Protocol

from ..domain import Entity, Fact, IngestResult, MemoryQuery, RawEvent, Relationship, Source


class MemoryStore(Protocol):
    """组织记忆存储层协议，定义所有后端实现必须提供的方法。

    实现类包括 InMemoryMemoryStore（测试用）和 LocalSQLiteMemoryStore（生产用）。
    """

    def upsert_entity(self, entity: Entity) -> None:
        """插入或更新实体（按 id 幂等）。"""
        ...

    def upsert_source(self, source: Source) -> None:
        """插入或更新来源记录（按 id 幂等）。"""
        ...

    def append_event(self, event: RawEvent) -> None:
        """追加原始事件（按 id 幂等，不覆盖已有事件）。"""
        ...

    def upsert_fact(self, fact: Fact) -> None:
        """插入或更新事实（按 id 幂等）。"""
        ...

    def upsert_relationship(self, relationship: Relationship) -> None:
        """插入或更新关系（按 id 幂等）。"""
        ...

    def apply_ingest_result(self, result: IngestResult) -> None:
        """批量写入一次摄入操作产生的所有领域对象。"""
        ...

    def search_facts(self, query: MemoryQuery) -> list:
        """按查询条件检索事实，结果已按权限过滤并按时间倒序排列。"""
        ...

    def list_events(self, query: MemoryQuery) -> list:
        """按查询条件列出原始事件，结果已按权限过滤并按时间倒序排列。"""
        ...

    def get_source(self, source_id: str) -> Optional[Source]:
        """按 ID 获取单个来源记录，不存在时返回 None。"""
        ...

    def audit(self, action: str, target_type: str, target_id: str, actor_id: str, reason: str) -> None:
        """记录审计日志，用于追踪敏感操作（如 break_glass 访问）。"""
        ...
