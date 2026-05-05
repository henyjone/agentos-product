"""存储层工具函数 —— 提供将 IngestResult 批量写入任意 MemoryStore 的通用辅助函数。"""

from ..domain import IngestResult
from .interface import MemoryStore


def apply_ingest_result(store: MemoryStore, result: IngestResult) -> None:
    """将 IngestResult 中的所有领域对象依次写入存储层。

    写入顺序：entities → sources → events → facts → relationships，
    保证外键依赖关系（如 fact 引用 source）在写入时已存在。
    """
    for entity in result.entities:
        store.upsert_entity(entity)
    for source in result.sources:
        store.upsert_source(source)
    for event in result.events:
        store.append_event(event)
    for fact in result.facts:
        store.upsert_fact(fact)
    for relationship in result.relationships:
        store.upsert_relationship(relationship)
