"""组织记忆核心领域模型 —— 定义实体、事件、事实、关系等数据结构及访问控制常量。"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# 作用域类型别名，控制数据的可见范围
Scope = str
# 敏感度类型别名，控制数据的访问权限
Sensitivity = str

# 作用域常量：个人 / 团队 / 组织 / 受限
SCOPE_PERSONAL = "personal"
SCOPE_TEAM = "team"
SCOPE_ORG = "org"
SCOPE_RESTRICTED = "restricted"

# 敏感度常量：公开 / 内部 / 私密 / 受限
SENSITIVITY_PUBLIC = "public"
SENSITIVITY_INTERNAL = "internal"
SENSITIVITY_PRIVATE = "private"
SENSITIVITY_RESTRICTED = "restricted"

# 置信度常量：高 / 中 / 低
CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"

# 合法值集合，用于校验输入
VALID_SCOPES = (SCOPE_PERSONAL, SCOPE_TEAM, SCOPE_ORG, SCOPE_RESTRICTED)
VALID_SENSITIVITIES = (
    SENSITIVITY_PUBLIC,
    SENSITIVITY_INTERNAL,
    SENSITIVITY_PRIVATE,
    SENSITIVITY_RESTRICTED,
)
VALID_CONFIDENCES = (CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW)


@dataclass(frozen=True)
class Entity:
    """组织记忆中的实体，可以是人员、项目、仓库、提交、文档等。"""

    id: str                                          # 全局唯一标识符，格式为 "type:value"
    type: str                                        # 实体类型，如 "person"、"project"、"repo"
    name: str                                        # 显示名称
    aliases: List[str] = field(default_factory=list) # 别名列表，用于跨系统关联
    owner_id: Optional[str] = None                   # 所有者实体 ID
    status: str = "active"                           # 实体状态，默认 active
    scope: Scope = SCOPE_TEAM
    sensitivity: Sensitivity = SENSITIVITY_INTERNAL
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class Source:
    """事实或事件的来源记录，追踪信息的原始出处。"""

    id: str                                         # 来源唯一标识符
    title: str                                      # 来源标题，如 commit message 第一行
    source_type: str                                # 来源类型，如 "code"、"document"
    system: str                                     # 来源系统，如 "gitea"、"commit_guide"
    url: str = ""                                   # 原始 URL，可选
    sensitivity: Sensitivity = SENSITIVITY_INTERNAL
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""


@dataclass(frozen=True)
class RawEvent:
    """原始事件记录，表示系统中发生的一次可观测活动（如提交、文档更新）。"""

    id: str
    event_type: str                    # 事件类型，如 "gitea_commit"、"commit_guide_submit"
    occurred_at: str                   # 事件发生时间（ISO 8601）
    ingested_at: str                   # 事件被摄入系统的时间
    actor_id: Optional[str] = None    # 触发事件的实体 ID
    project_id: Optional[str] = None  # 关联项目 ID
    repo_id: Optional[str] = None     # 关联仓库 ID
    source_id: Optional[str] = None   # 关联来源 ID
    scope: Scope = SCOPE_TEAM
    sensitivity: Sensitivity = SENSITIVITY_INTERNAL
    payload: Dict[str, Any] = field(default_factory=dict)  # 事件详细数据


@dataclass(frozen=True)
class Fact:
    """从事件中提炼出的结构化事实，是组织记忆的核心存储单元。"""

    id: str
    fact_type: str                              # 事实类型，如 "employee_completed_work"
    content: str                                # 事实的自然语言描述
    source_ids: List[str]                       # 支撑该事实的来源 ID 列表
    confidence: str                             # 置信度：high / medium / low
    subject_entity_id: Optional[str] = None    # 事实的主体实体 ID（通常是人员）
    object_entity_id: Optional[str] = None     # 事实的客体实体 ID（通常是项目）
    project_id: Optional[str] = None
    scope: Scope = SCOPE_TEAM
    sensitivity: Sensitivity = SENSITIVITY_INTERNAL
    valid_from: Optional[str] = None           # 事实有效期起始日期
    valid_to: Optional[str] = None             # 事实有效期结束日期，None 表示持续有效
    created_by: str = ""                       # 创建者标识，如 "rule:commit_event"
    status: str = "active"                     # 事实状态：active / needs_review / archived
    created_at: str = ""
    updated_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Relationship:
    """实体间的关系记录，如"人员 works_on 项目"。"""

    id: str
    from_entity_id: str                              # 关系起点实体 ID
    to_entity_id: str                                # 关系终点实体 ID
    relation_type: str                               # 关系类型，如 "works_on"、"belongs_to"
    source_ids: List[str] = field(default_factory=list)
    confidence: str = CONFIDENCE_MEDIUM
    scope: Scope = SCOPE_TEAM
    sensitivity: Sensitivity = SENSITIVITY_INTERNAL
    created_at: str = ""
    updated_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IngestResult:
    """一次数据摄入操作产生的所有领域对象集合，用于批量写入存储层。"""

    entities: List[Entity] = field(default_factory=list)
    sources: List[Source] = field(default_factory=list)
    events: List[RawEvent] = field(default_factory=list)
    facts: List[Fact] = field(default_factory=list)
    relationships: List[Relationship] = field(default_factory=list)


@dataclass(frozen=True)
class ExtractionResult:
    """事实提取器的输出结果，包含提取到的事实、关系和错误信息。"""

    facts: List[Fact] = field(default_factory=list)
    relationships: List[Relationship] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)  # 提取过程中的非致命错误


@dataclass(frozen=True)
class MemoryQuery:
    """组织记忆查询参数，支持按用户、角色、项目、时间范围等多维度过滤。"""

    user_id: str                                    # 发起查询的用户 ID，用于权限校验
    role: str = "employee"                          # 用户角色，决定可读范围
    project_ids: List[str] = field(default_factory=list)
    person_ids: List[str] = field(default_factory=list)
    fact_types: List[str] = field(default_factory=list)
    source_types: List[str] = field(default_factory=list)
    scopes: List[Scope] = field(default_factory=list)
    time_from: Optional[str] = None                # 时间范围起始（ISO 日期字符串）
    time_to: Optional[str] = None                  # 时间范围结束（ISO 日期字符串）
    limit: int = 50
    break_glass: bool = False                       # 紧急访问标志，需配合 reason 使用
    reason: str = ""                                # break_glass 时必须提供的访问原因
