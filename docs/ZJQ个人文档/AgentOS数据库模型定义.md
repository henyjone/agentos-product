# AgentOS 数据库模型定义（Dev1 Java 版）

## 1. 文档定位

本文档承接 `AgentOS服务设计方案.md`，只维护数据库模型、核心表结构、关联表、索引建议和落库约束。

不在本文档中维护：

- HTTP API 路径
- 前后端响应结构
- Agent 请求与响应 Schema
- 错误码与分页契约

上述内容统一放在 `AgentOS接口契约与Schema定义.md`。

## 2. 建模原则

- 数据模型优先服务 MVP 闭环，不做过度设计
- 核心实体与治理实体分开建模
- 审计日志采用只追加模型
- 敏感数据必须显式标注敏感等级和可见范围
- 表结构命名与接口字段尽量保持一致，降低 DTO 转换成本

## 3. 公共枚举

```text
Role（角色）:
- admin（系统管理员）
- executive（高层管理者）
- manager（团队负责人）
- employee（普通员工）
- hr（人力角色）

Sensitivity（敏感等级）:
- public（公开）
- internal（内部）
- private（私人）
- restricted（受限）

ApprovalStatus（审批状态）:
- pending（待审批）
- approved（已批准）
- rejected（已拒绝）
- expired（已过期）
- executing（执行中）
- executed（已执行成功）
- execution_failed（执行失败）
- cancelled（已取消）

TaskStatus（任务状态）:
- pending（待处理）
- in_progress（进行中）
- blocked（阻塞中）
- completed（已完成）
- cancelled（已取消）

MeetingStatus（会议状态）:
- scheduled（已安排）
- running（进行中）
- completed（已结束）
- cancelled（已取消）

MemoryStatus（记忆状态）:
- active（有效）
- archived（已归档）
- deleted（已删除）
```

## 4. 公共字段约定

所有核心主表统一保留以下字段：

```text
id: UUID
org_id: UUID
created_at: timestamptz
updated_at: timestamptz
created_by: UUID
updated_by: UUID
version: integer
```

涉及权限和敏感数据的对象额外建议保留：

```text
sensitivity: public | internal | private | restricted
visibility_scope: self | team | org | specific_users
metadata: jsonb
```

## 5. 核心实体定义

### 5.1 `Org` 组织

用途：组织租户根实体，作为权限与数据隔离边界。

| 字段 | 类型 | 说明 |
| :-- | :-- | :-- |
| `id` | UUID | 组织 ID |
| `name` | varchar(100) | 组织名称 |
| `code` | varchar(50) | 组织编码，唯一 |
| `domain` | varchar(100) | 企业邮箱后缀 |
| `status` | varchar(20) | `active/inactive` |
| `settings` | jsonb | 组织级配置、审批策略、开关 |
| `created_at` | timestamptz | 创建时间 |
| `updated_at` | timestamptz | 更新时间 |

建议索引：

- `UNIQUE(code)`
- `INDEX(status)`

### 5.2 `User` 用户

用途：平台用户主体，也是 Agent 请求中的当前身份。

| 字段 | 类型 | 说明 |
| :-- | :-- | :-- |
| `id` | UUID | 用户 ID |
| `org_id` | UUID | 所属组织 |
| `team_id` | UUID | 当前主团队 |
| `manager_id` | UUID | 直属上级 |
| `email` | varchar(150) | 登录邮箱，组织内唯一 |
| `username` | varchar(50) | 用户名 |
| `display_name` | varchar(100) | 展示名 |
| `role` | varchar(20) | `admin/executive/manager/employee/hr` |
| `title` | varchar(100) | 岗位 |
| `status` | varchar(20) | `active/inactive/suspended` |
| `last_login_at` | timestamptz | 最近登录时间 |
| `profile` | jsonb | 头像、时区、偏好 |
| `created_at` | timestamptz | 创建时间 |
| `updated_at` | timestamptz | 更新时间 |

关键约束：

- 一个用户只保留一个主角色，MVP 不做多角色混合
- `HR` 不默认读取员工私人原始记忆
- `Executive` 不默认读取员工私聊、私人记忆、原始会议明细

### 5.3 `Team` 团队

用途：权限过滤和工作聚合的基础边界。

| 字段 | 类型 | 说明 |
| :-- | :-- | :-- |
| `id` | UUID | 团队 ID |
| `org_id` | UUID | 所属组织 |
| `name` | varchar(100) | 团队名称 |
| `code` | varchar(50) | 团队编码 |
| `leader_id` | UUID | 团队负责人 |
| `parent_team_id` | UUID | 上级团队，可空 |
| `status` | varchar(20) | `active/inactive` |
| `member_count` | integer | 冗余成员计数 |
| `created_at` | timestamptz | 创建时间 |
| `updated_at` | timestamptz | 更新时间 |

### 5.4 `Project` 项目

用途：管理视图、项目状态助手和跨团队协作的核心实体。

| 字段 | 类型 | 说明 |
| :-- | :-- | :-- |
| `id` | UUID | 项目 ID |
| `org_id` | UUID | 所属组织 |
| `team_id` | UUID | 归属团队 |
| `owner_id` | UUID | 项目负责人 |
| `name` | varchar(150) | 项目名称 |
| `code` | varchar(50) | 项目编码 |
| `status` | varchar(30) | `planning/active/blocked/on_hold/completed` |
| `priority` | varchar(20) | 优先级 |
| `visibility` | varchar(20) | `team/org/specific_users` |
| `summary` | text | 项目概述 |
| `risk_level` | varchar(20) | `low/medium/high/critical` |
| `start_date` | date | 开始日期 |
| `due_date` | date | 截止日期 |
| `metadata` | jsonb | 外部映射、标签 |

### 5.5 `Task` 任务

用途：承接 Agent 创建任务、项目任务同步和个人简报。

| 字段 | 类型 | 说明 |
| :-- | :-- | :-- |
| `id` | UUID | 任务 ID |
| `org_id` | UUID | 所属组织 |
| `project_id` | UUID | 所属项目，可空 |
| `team_id` | UUID | 所属团队 |
| `assignee_id` | UUID | 负责人 |
| `reporter_id` | UUID | 发起人 |
| `source_connector_id` | UUID | 来源 Connector，可空 |
| `title` | varchar(200) | 任务标题 |
| `description` | text | 任务描述 |
| `status` | varchar(20) | `pending/in_progress/blocked/completed/cancelled` |
| `priority` | varchar(20) | `low/medium/high/critical` |
| `sensitivity` | varchar(20) | 敏感等级 |
| `due_at` | timestamptz | 截止时间 |
| `completed_at` | timestamptz | 完成时间 |
| `metadata` | jsonb | 外部单号、原始字段 |

实现约束：

- Agent 创建正式任务默认属于高风险写动作
- 员工只能编辑自己负责的任务
- 管理者可编辑自己团队任务

### 5.6 `Meeting` 会议

用途：会议纪要、知识来源、管理摘要输入。

| 字段 | 类型 | 说明 |
| :-- | :-- | :-- |
| `id` | UUID | 会议 ID |
| `org_id` | UUID | 所属组织 |
| `team_id` | UUID | 所属团队，可空 |
| `project_id` | UUID | 关联项目，可空 |
| `host_id` | UUID | 主持人 |
| `title` | varchar(200) | 会议标题 |
| `status` | varchar(20) | `scheduled/running/completed/cancelled` |
| `started_at` | timestamptz | 开始时间 |
| `ended_at` | timestamptz | 结束时间 |
| `summary` | text | 结构化摘要 |
| `notes` | text | 原始纪要 |
| `sensitivity` | varchar(20) | 敏感等级 |
| `participant_ids` | jsonb | 参会人列表 |
| `source_connector_id` | UUID | 来源 Connector，可空 |

实现约束：

- `Executive` 和 `Manager` 默认看到聚合摘要
- 原始纪要进入知识检索前必须经过权限和敏感等级过滤

### 5.7 `Memory` 记忆

用途：个人、团队、组织层的长期或中期记忆，是 Agent 上下文的重要来源。

| 字段 | 类型 | 说明 |
| :-- | :-- | :-- |
| `id` | UUID | 记忆 ID |
| `org_id` | UUID | 所属组织 |
| `owner_id` | UUID | 所有者 |
| `team_id` | UUID | 团队范围，可空 |
| `project_id` | UUID | 项目范围，可空 |
| `memory_type` | varchar(20) | `session/midterm/longterm` |
| `section` | varchar(50) | 如系统规则、项目上下文、个人偏好 |
| `title` | varchar(200) | 标题 |
| `content` | text | 记忆正文 |
| `status` | varchar(20) | `active/archived/deleted` |
| `sensitivity` | varchar(20) | `public/internal/private/restricted` |
| `visibility_scope` | varchar(20) | `self/team/org/specific_users` |
| `source_connector_id` | UUID | 来源，可空 |
| `source_refs` | jsonb | 来源引用列表 |
| `last_accessed_at` | timestamptz | 最近读取时间 |
| `metadata` | jsonb | 召回标签、权重、过期策略 |

关键约束：

- 个人原始记忆默认 `private`
- 管理层和 HR 不能默认读取员工 `private/restricted` 原始记忆
- `restricted` 记忆不允许进入普通 Agent 上下文
- 访问 `restricted` 记忆必须走 break-glass

### 5.8 `Approval` 审批

用途：承接高风险 Agent 动作的人审队列。

| 字段 | 类型 | 说明 |
| :-- | :-- | :-- |
| `id` | UUID | 审批 ID |
| `org_id` | UUID | 所属组织 |
| `requester_id` | UUID | 发起人 |
| `reviewer_id` | UUID | 审批人，可空 |
| `action_id` | UUID | 关联动作记录 |
| `status` | varchar(30) | 审批状态 |
| `risk_level` | varchar(20) | 风险等级 |
| `sensitivity` | varchar(20) | 关联数据敏感等级 |
| `reason` | text | 发起原因 |
| `decision_reason` | text | 审批意见 |
| `scope_snapshot` | jsonb | 影响范围快照 |
| `payload_snapshot` | jsonb | 动作载荷快照 |
| `expires_at` | timestamptz | 过期时间 |
| `decided_at` | timestamptz | 审批时间 |
| `executed_at` | timestamptz | 执行完成时间 |
| `execution_result` | jsonb | 执行结果或失败原因 |

### 5.9 `AuditEvent` 审计事件

用途：只追加追踪日志，覆盖读取、生成、审批、执行、越权和异常。

| 字段 | 类型 | 说明 |
| :-- | :-- | :-- |
| `id` | UUID | 审计事件 ID |
| `org_id` | UUID | 所属组织 |
| `actor_id` | UUID | 触发者，可为系统代理 |
| `actor_type` | varchar(20) | `user/agent/system` |
| `event_type` | varchar(50) | 审计事件类型 |
| `target_type` | varchar(50) | 目标对象类型 |
| `target_id` | UUID | 目标对象 ID，可空 |
| `request_id` | varchar(64) | 请求链路 ID |
| `approval_id` | UUID | 关联审批，可空 |
| `result` | varchar(20) | `success/failed/denied/pending` |
| `risk_level` | varchar(20) | 风险等级 |
| `sensitivity` | varchar(20) | 敏感等级 |
| `summary` | text | 审计摘要 |
| `details` | jsonb | 扩展字段 |
| `occurred_at` | timestamptz | 发生时间 |

### 5.10 `ConnectorSource` 数据来源

用途：统一描述外部数据源、同步状态和来源追溯信息。

| 字段 | 类型 | 说明 |
| :-- | :-- | :-- |
| `id` | UUID | Connector ID |
| `org_id` | UUID | 所属组织 |
| `type` | varchar(50) | `gitea/notion/jira/feishu/email/manual` |
| `name` | varchar(100) | 来源名称 |
| `status` | varchar(20) | `active/inactive/error` |
| `owner_id` | UUID | 维护负责人 |
| `base_url` | text | 来源地址 |
| `permission_scope` | varchar(20) | `org/team/user` |
| `default_sensitivity` | varchar(20) | 默认敏感等级 |
| `auth_config` | jsonb | 脱敏认证配置 |
| `sync_cursor` | jsonb | 增量同步游标 |
| `last_synced_at` | timestamptz | 最近同步时间 |
| `metadata` | jsonb | 来源描述、映射规则 |

## 6. 关系表建议

```text
project_members
team_members
meeting_participants
approval_access_grants
```

### 6.1 `project_members`

用途：维护项目成员关系，支持跨团队协作和权限过滤。

建议字段：

- `id`
- `org_id`
- `project_id`
- `user_id`
- `member_role`
- `created_at`

### 6.2 `team_members`

用途：维护团队归属与团队层权限聚合。

建议字段：

- `id`
- `org_id`
- `team_id`
- `user_id`
- `member_role`
- `joined_at`

### 6.3 `meeting_participants`

用途：维护会议参与关系，支持会议可见性过滤和来源追溯。

建议字段：

- `id`
- `org_id`
- `meeting_id`
- `user_id`
- `participant_role`

### 6.4 `approval_access_grants`

用途：记录 break-glass 或受控访问后的临时授权。

建议字段：

- `id`
- `org_id`
- `approval_id`
- `grantee_id`
- `target_type`
- `target_id`
- `fields`
- `granted_at`
- `expires_at`

## 7. 建议索引

- `users(org_id, role, status)`
- `projects(org_id, team_id, status)`
- `tasks(org_id, assignee_id, status, due_at)`
- `meetings(org_id, project_id, started_at)`
- `memories(org_id, owner_id, sensitivity, status)`
- `approvals(org_id, status, reviewer_id, expires_at)`
- `audit_events(org_id, occurred_at, event_type, actor_id)`
- `connector_sources(org_id, type, status)`

## 8. 存储建议

- `Memory.content` 可做全文索引
- `Memory.source_refs` 和 `AuditEvent.details` 使用 `jsonb`
- 审计事件采用只追加，不做物理更新
- `restricted` 相关字段建议列级加密或应用层加密
- 高频列表页优先通过组合索引和投影视图优化

## 9. Java 落地建议

- Entity 与 API DTO 分离，避免数据库结构直接暴露给前端和 Agent
- 审批、审计、记忆等对象建议保留独立的 assembler / mapper
- `jsonb` 字段在 Java 中统一封装，避免散落为无约束字符串
- 审计表写入链路应单向只追加，服务层禁止更新历史记录

## 10. 结论

本文档承担 Dev1 的数据库模型基线职责，后续如果出现以下变更，应优先更新本文档：

- 核心实体新增或删除
- 表字段新增、改名、删除
- 关联关系调整
- 索引和存储策略调整
- 敏感数据落库策略调整
