"""事实提取模块 —— 从 RawEvent 中提炼结构化 Fact 和 Relationship。

提供两种实现：
- RuleFactExtractor：基于规则的确定性提取，用于测试和安全降级
- AIFactExtractor：基于 LLM 的语义提取，置信度更高但依赖外部 API
"""

import json
import re
from typing import Dict, Iterable, List, Optional, Protocol

from ..domain import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    ExtractionResult,
    Fact,
    RawEvent,
    Relationship,
    SENSITIVITY_INTERNAL,
    SCOPE_TEAM,
    VALID_CONFIDENCES,
    VALID_SCOPES,
    VALID_SENSITIVITIES,
)
from ..ids import fact_id, relationship_id
from ..time_utils import utc_now_iso


class FactExtractor(Protocol):
    """事实提取器协议，所有实现必须提供 extract 方法。"""

    def extract(self, events: Iterable[RawEvent]) -> ExtractionResult:
        ...


class RuleFactExtractor:
    """基于规则的确定性事实提取器，不依赖外部 API，适合测试和安全降级场景。"""

    def extract(self, events: Iterable[RawEvent]) -> ExtractionResult:
        """从事件列表中提取事实和关系。

        支持的事件类型：
        - gitea_commit / commit_guide_submit → employee_completed_work 事实 + works_on 关系
        - project_doc_update → source_summary 事实
        """
        facts: List[Fact] = []
        relationships: List[Relationship] = []
        for event in events:
            if event.event_type in ("gitea_commit", "commit_guide_submit"):
                fact = self._commit_work_fact(event)
                if fact:
                    facts.append(fact)
                relationship = self._works_on_relationship(event)
                if relationship:
                    relationships.append(relationship)
            elif event.event_type == "project_doc_update":
                fact = self._project_doc_fact(event)
                if fact:
                    facts.append(fact)
        return ExtractionResult(facts=facts, relationships=relationships)

    def _commit_work_fact(self, event: RawEvent) -> Optional[Fact]:
        """从提交事件中提取"员工完成了某项工作"的事实。"""
        if not event.actor_id or not event.project_id or not event.source_id:
            return None
        message = str(event.payload.get("message") or event.payload.get("commit_message") or "").strip()
        description = _clean_commit_message(message)
        if not description:
            description = "提交了代码变更"
        repo_name = str(event.payload.get("repo") or event.repo_id or "").replace("repo:", "")
        content = "{0} 完成了 {1}".format(_entity_label(event.actor_id), description)
        if repo_name:
            content = "{0}（仓库：{1}）".format(content, repo_name)
        now = utc_now_iso()
        return Fact(
            id=fact_id("employee_completed_work", event.actor_id, event.project_id, event.source_id),
            fact_type="employee_completed_work",
            content=content,
            subject_entity_id=event.actor_id,
            object_entity_id=event.project_id,
            project_id=event.project_id,
            source_ids=[event.source_id],
            confidence=_confidence_for_commit_event(event),
            scope=event.scope,
            sensitivity=event.sensitivity,
            valid_from=event.occurred_at[:10] if event.occurred_at else None,
            created_by="rule:commit_event",
            created_at=now,
            updated_at=now,
            metadata={
                "event_id": event.id,
                "event_type": event.event_type,
            },
        )

    def _works_on_relationship(self, event: RawEvent) -> Optional[Relationship]:
        """从提交事件中提取"人员参与项目"的关系。"""
        if not event.actor_id or not event.project_id:
            return None
        now = utc_now_iso()
        source_ids = [event.source_id] if event.source_id else []
        return Relationship(
            id=relationship_id(event.actor_id, "works_on", event.project_id),
            from_entity_id=event.actor_id,
            to_entity_id=event.project_id,
            relation_type="works_on",
            source_ids=source_ids,
            # 有来源证据时置信度更高
            confidence=CONFIDENCE_HIGH if source_ids else CONFIDENCE_MEDIUM,
            scope=event.scope,
            sensitivity=event.sensitivity,
            created_at=now,
            updated_at=now,
        )

    def _project_doc_fact(self, event: RawEvent) -> Optional[Fact]:
        """从文档更新事件中提取"文档已纳入组织记忆"的事实。"""
        if not event.project_id or not event.source_id:
            return None
        doc_path = str(event.payload.get("path") or "project document")
        title = str(event.payload.get("title") or doc_path)
        now = utc_now_iso()
        return Fact(
            id=fact_id("source_summary", event.project_id, event.source_id),
            fact_type="source_summary",
            content="项目文档已纳入组织记忆上下文：{0}".format(title),
            object_entity_id=event.project_id,
            project_id=event.project_id,
            source_ids=[event.source_id],
            confidence=CONFIDENCE_MEDIUM,
            scope=event.scope,
            sensitivity=event.sensitivity,
            valid_from=event.occurred_at[:10] if event.occurred_at else None,
            created_by="rule:project_doc",
            created_at=now,
            updated_at=now,
            metadata={"event_id": event.id, "path": doc_path},
        )


class ModelClient(Protocol):
    """AI 模型客户端协议，AIFactExtractor 依赖此接口调用 LLM。"""

    def generate(self, messages: List[Dict], temperature: float, max_output_tokens: int, response_format: str) -> str:
        ...


class AIFactExtractor:
    """基于 LLM 的事实提取器，输出模型与 RuleFactExtractor 相同。

    调用 LLM 对事件列表进行语义分析，提取更丰富的事实和关系。
    LLM 调用失败时返回包含错误信息的 ExtractionResult，不抛出异常。
    """

    def __init__(self, model_client: ModelClient):
        self.model_client = model_client

    def extract(self, events: Iterable[RawEvent]) -> ExtractionResult:
        """调用 LLM 从事件列表中提取事实和关系，解析 JSON 响应并校验字段。"""
        event_list = list(events)
        if not event_list:
            return ExtractionResult()
        try:
            raw = self.model_client.generate(
                messages=[
                    {"role": "system", "content": _AI_SYSTEM_PROMPT},
                    {"role": "user", "content": _events_to_json(event_list)},
                ],
                temperature=0.2,
                max_output_tokens=4096,
                response_format="json",
            )
            data = _parse_json(raw)
        except Exception as exc:
            return ExtractionResult(errors=["ai_fact_extractor_failed: {0}".format(exc)])

        facts: List[Fact] = []
        relationships: List[Relationship] = []
        errors: List[str] = []
        for item in data.get("facts", []):
            if not isinstance(item, dict):
                errors.append("invalid_fact_item: item is not an object")
                continue
            try:
                facts.append(_fact_from_dict(item))
            except Exception as exc:
                errors.append("invalid_fact_item: {0}".format(exc))
        for item in data.get("relationships", []):
            if not isinstance(item, dict):
                errors.append("invalid_relationship_item: item is not an object")
                continue
            try:
                relationships.append(_relationship_from_dict(item))
            except Exception as exc:
                errors.append("invalid_relationship_item: {0}".format(exc))
        return ExtractionResult(facts=facts, relationships=relationships, errors=errors)


def _confidence_for_commit_event(event: RawEvent) -> str:
    """根据事件 payload 中的证据丰富程度推断置信度。

    有 patch/diff 内容 → high；有文件列表或 message → medium；否则 → low。
    """
    if (
        event.payload.get("patch_excerpt")
        or event.payload.get("file_snapshots")
        or event.payload.get("diff_context")
        or event.payload.get("has_patch")
    ):
        return CONFIDENCE_HIGH
    if event.payload.get("files") or event.payload.get("staged_files"):
        return CONFIDENCE_MEDIUM
    if event.payload.get("message") or event.payload.get("commit_message"):
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


def _clean_commit_message(message: str) -> str:
    """去除 Conventional Commit 前缀（如 feat(scope):），保留描述部分。"""
    first_line = message.splitlines()[0].strip() if message else ""
    first_line = re.sub(r"^(feat|fix|refactor|docs|test|chore|perf|revert)(\([^)]+\))?:\s*", "", first_line)
    return first_line.rstrip("。；;")


def _entity_label(entity_id: str) -> str:
    """从 entity_id（如 "person:alice"）中提取可读标签（"alice"）。"""
    return entity_id.split(":", 1)[1] if ":" in entity_id else entity_id


def _events_to_json(events: List[RawEvent]) -> str:
    """将 RawEvent 列表序列化为 JSON 字符串，供 LLM 分析。"""
    payload = [
        {
            "id": event.id,
            "event_type": event.event_type,
            "actor_id": event.actor_id,
            "project_id": event.project_id,
            "repo_id": event.repo_id,
            "source_id": event.source_id,
            "scope": event.scope,
            "sensitivity": event.sensitivity,
            "occurred_at": event.occurred_at,
            "payload": event.payload,
        }
        for event in events
    ]
    return json.dumps({"events": payload}, ensure_ascii=False)


def _parse_json(raw: str) -> Dict:
    """解析 LLM 输出的 JSON，自动去除可能的 ``` 代码块包裹。"""
    text = str(raw or "").strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("AI fact extractor response root must be an object")
    return data


def _fact_from_dict(item: Dict) -> Fact:
    """从字典构建 Fact 对象，缺少 source_ids 时降级置信度并标记 needs_review。"""
    now = utc_now_iso()
    content = str(item.get("content") or "").strip()
    if not content:
        raise ValueError("content is required")
    source_ids = _source_ids(item.get("source_ids", []))
    metadata = dict(item.get("metadata") or {})
    confidence = _normalize(item.get("confidence"), VALID_CONFIDENCES, CONFIDENCE_LOW)
    status = str(item.get("status") or "active")
    if not source_ids:
        # 无来源证据时降级置信度并标记需要人工审核
        validation_errors = metadata.get("validation_errors")
        if not isinstance(validation_errors, list):
            validation_errors = []
        validation_errors.append("missing_source_ids")
        metadata["validation_errors"] = validation_errors
        confidence = CONFIDENCE_LOW
        status = "needs_review"
    return Fact(
        id=str(item.get("id") or fact_id(item.get("fact_type", "ai_fact"), content[:40])),
        fact_type=str(item.get("fact_type") or "source_summary"),
        content=content,
        source_ids=source_ids,
        confidence=confidence,
        subject_entity_id=item.get("subject_entity_id"),
        object_entity_id=item.get("object_entity_id"),
        project_id=item.get("project_id"),
        scope=_normalize(item.get("scope"), VALID_SCOPES, SCOPE_TEAM),
        sensitivity=_normalize(item.get("sensitivity"), VALID_SENSITIVITIES, SENSITIVITY_INTERNAL),
        valid_from=item.get("valid_from"),
        valid_to=item.get("valid_to"),
        created_by=str(item.get("created_by") or "ai:fact_extractor"),
        status=status,
        created_at=str(item.get("created_at") or now),
        updated_at=str(item.get("updated_at") or now),
        metadata=metadata,
    )


def _relationship_from_dict(item: Dict) -> Relationship:
    """从字典构建 Relationship 对象，端点 ID 不能为空。"""
    now = utc_now_iso()
    from_entity_id = str(item.get("from_entity_id") or "")
    to_entity_id = str(item.get("to_entity_id") or "")
    relation_type = str(item.get("relation_type") or "mentions")
    if not from_entity_id or not to_entity_id:
        raise ValueError("relationship endpoints are required")
    return Relationship(
        id=str(item.get("id") or relationship_id(from_entity_id, relation_type, to_entity_id)),
        from_entity_id=from_entity_id,
        to_entity_id=to_entity_id,
        relation_type=relation_type,
        source_ids=_source_ids(item.get("source_ids", [])),
        confidence=_normalize(item.get("confidence"), VALID_CONFIDENCES, CONFIDENCE_LOW),
        scope=_normalize(item.get("scope"), VALID_SCOPES, SCOPE_TEAM),
        sensitivity=_normalize(item.get("sensitivity"), VALID_SENSITIVITIES, SENSITIVITY_INTERNAL),
        created_at=str(item.get("created_at") or now),
        updated_at=str(item.get("updated_at") or now),
        metadata=dict(item.get("metadata") or {}),
    )


def _normalize(value, allowed, default: str) -> str:
    """将值规范化为 allowed 集合中的成员，不合法时返回 default。"""
    candidate = str(value or "").strip().lower()
    return candidate if candidate in allowed else default


def _source_ids(value) -> List[str]:
    """从任意值中提取非空字符串列表，用于解析 source_ids 字段。"""
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


_AI_SYSTEM_PROMPT = """你是 AgentOS 的组织记忆事实提炼器。
你会收到 RawEvent 列表，请只输出 JSON。

要求：
1. 只从输入事件提炼事实，不要编造。
2. 每条 high confidence fact 必须有 source_ids。
3. 如果只有 commit message，最高 confidence 为 medium。
4. 如果有 patch_excerpt、file_snapshots、has_patch=true 或 diff_context 非空，可以给 high。
5. 私人或受限事件必须保留原 scope/sensitivity。

输出结构：
{
  "facts": [],
  "relationships": []
}
"""
