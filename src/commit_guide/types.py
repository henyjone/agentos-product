"""提交类型定义模块 —— 定义 Conventional Commit 规范的类型枚举、格式化与校验工具。"""

import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class CommitType:
    """单个提交类型的元数据，用于 CLI 展示和格式化。"""

    key: str          # 类型标识符，如 "feat"、"fix"，写入 commit message
    description: str  # 中文描述，仅用于 CLI 交互展示
    emoji: str = ""


# 支持的提交类型列表，顺序决定 CLI 手动编辑时的展示顺序
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

# 校验 commit message 第一行格式的正则：type(scope): description
# description 长度限制 5-100 字符，scope 括号可选
COMMIT_MESSAGE_PATTERN = re.compile(
    r"^(feat|fix|refactor|docs|test|chore|perf|revert)(\([^)]+\))?: .{5,100}$"
)


def get_commit_types() -> List[CommitType]:
    """返回所有支持的提交类型列表（副本）。"""
    return list(COMMIT_TYPES)


def get_type_by_key(key: str) -> Optional[CommitType]:
    """按 key 查找提交类型，不存在返回 None。"""
    for item in COMMIT_TYPES:
        if item.key == key:
            return item
    return None


def is_valid_type(key: str) -> bool:
    """判断 key 是否为合法的提交类型标识符。"""
    return key in _TYPE_KEYS


def normalize_description(description: str) -> str:
    """去除首尾空白并合并内部连续空格，用于规范化用户输入的描述文本。"""
    return " ".join(description.strip().split())


def format_commit_message(type_key: str, scope: Optional[str], description: str) -> str:
    """将 type、scope、description 组合为标准 Conventional Commit 第一行。

    超过 100 字符的描述会被截断；scope 为空时省略括号部分。
    """
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
    """校验 commit message 第一行是否符合 Conventional Commit 格式规范。"""
    subject = message.strip().splitlines()[0].strip() if message.strip() else ""
    return bool(COMMIT_MESSAGE_PATTERN.match(subject))
