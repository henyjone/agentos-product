"""ID 生成工具模块 —— 为各类领域对象生成结构化、URL 安全的唯一标识符。"""

import hashlib
import re


# 允许出现在 ID 中的字符集，其余字符会被替换为下划线
_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def safe_id(value: str) -> str:
    """将任意字符串转换为 URL 安全的 ID 片段。

    处理步骤：
    1. 将路径分隔符（\\、/、:）替换为连字符
    2. 其余非法字符替换为下划线
    3. 合并连续的连字符和下划线
    4. 若结果为空，则对原始值取 SHA-1 前 10 位作为 fallback
    """
    raw = str(value or "").strip()
    text = raw
    text = text.replace("\\", "-").replace("/", "-").replace(":", "-")
    text = _SAFE_ID_RE.sub("_", text)
    text = re.sub(r"-+", "-", text)
    text = re.sub(r"_+", "_", text).strip("-_")
    if text:
        return text
    if raw:
        # 原始值非空但全部字符都被过滤掉时，用哈希保证唯一性
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
        return "id_{0}".format(digest)
    return "unknown"


def entity_id(entity_type: str, value: str) -> str:
    """生成实体 ID，格式为 "type:value"，如 "person:alice"。"""
    return "{0}:{1}".format(safe_id(entity_type), safe_id(value))


def source_id(system: str, source_type: str, value: str) -> str:
    """生成来源 ID，格式为 "source:system:type:value"。"""
    return "source:{0}:{1}:{2}".format(safe_id(system), safe_id(source_type), safe_id(value))


def event_id(event_type: str, value: str) -> str:
    """生成事件 ID，格式为 "event:type:value"。"""
    return "event:{0}:{1}".format(safe_id(event_type), safe_id(value))


def fact_id(fact_type: str, *parts: str) -> str:
    """生成事实 ID，格式为 "fact:type:part1:part2:..."，忽略空 part。"""
    return "fact:{0}:{1}".format(safe_id(fact_type), ":".join(safe_id(part) for part in parts if part))


def relationship_id(from_entity_id: str, relation_type: str, to_entity_id: str) -> str:
    """生成关系 ID，格式为 "rel:from:type:to"，确保同一关系幂等。"""
    return "rel:{0}:{1}:{2}".format(safe_id(from_entity_id), safe_id(relation_type), safe_id(to_entity_id))
