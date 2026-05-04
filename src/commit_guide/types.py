import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class CommitType:
    key: str
    description: str
    emoji: str = ""


COMMIT_TYPES: List[CommitType] = [
    CommitType("feat", "新功能"),
    CommitType("fix", "修复 bug"),
    CommitType("refactor", "重构"),
    CommitType("docs", "文档变更"),
    CommitType("test", "测试相关"),
    CommitType("chore", "构建、依赖、配置等杂项"),
    CommitType("perf", "性能优化"),
    CommitType("revert", "回滚"),
]

_TYPE_KEYS = {item.key for item in COMMIT_TYPES}
COMMIT_TYPE_KEYS = sorted(_TYPE_KEYS)  # 公开导出，供 ai_assist 等模块使用
COMMIT_MESSAGE_PATTERN = re.compile(
    r"^(feat|fix|refactor|docs|test|chore|perf|revert)(\([^)]+\))?: .{5,100}$"
)


def get_commit_types() -> List[CommitType]:
    return list(COMMIT_TYPES)


def get_type_by_key(key: str) -> Optional[CommitType]:
    for item in COMMIT_TYPES:
        if item.key == key:
            return item
    return None


def is_valid_type(key: str) -> bool:
    return key in _TYPE_KEYS


def normalize_description(description: str) -> str:
    return " ".join(description.strip().split())


def format_commit_message(type_key: str, scope: Optional[str], description: str) -> str:
    if not is_valid_type(type_key):
        raise ValueError("invalid commit type: {0}".format(type_key))

    clean_description = normalize_description(description)
    if not clean_description:
        raise ValueError("description must not be empty")
    if len(clean_description) < 5:
        raise ValueError("description must be at least 5 characters")
    if len(clean_description) > 100:
        clean_description = clean_description[:100]

    clean_scope = (scope or "").strip()
    if clean_scope:
        return "{0}({1}): {2}".format(type_key, clean_scope, clean_description)
    return "{0}: {1}".format(type_key, clean_description)


def is_valid_commit_message(message: str) -> bool:
    subject = message.strip().splitlines()[0].strip() if message.strip() else ""
    return bool(COMMIT_MESSAGE_PATTERN.match(subject))
