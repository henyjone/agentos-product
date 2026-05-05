# AgentOS 接口契约与 Schema 定义（Dev1 Java 版）

## 1. 文档定位

本文档用于维护 Dev1 后端对 Dev2、Dev3、Dev4 和 QA 暴露的接口契约与共享 Schema。

本文档负责：

- HTTP API 分组与路径约定
- 请求和响应包结构
- 共享 Schema 定义
- 审批状态流转
- 审计事件枚举
- 权限相关的契约级返回约束

本文档不负责：

- 方案设计动机和系统分层
- 数据库实体字段落库细节

对应文档：

- 方案设计：`AgentOS服务设计方案.md`
- 数据模型：`AgentOS数据库模型定义.md`
- 冻结治理：`Dev1-跨团队Schema冻结方案.md`

## 2. 契约统一规则

### 2.1 路径规则

- 所有接口统一使用 `/api/v1/...`
- 路径参数统一采用 OpenAPI 风格，如 `/users/{id}`
- 不再使用混合风格的 `:id`

### 2.2 字段规则

- JSON 字段统一使用 `snake_case`
- 时间统一使用 `ISO-8601 UTC`
- 主键统一使用 `UUID` 字符串
- 所有跨团队共享对象建议携带 `schema_version`

### 2.3 权限规则

- 所有响应默认经过服务端权限过滤
- `restricted` 资源默认不返回正文
- 涉及来源的数据对象必须带来源引用
- 涉及敏感内容的对象必须带 `sensitivity`

### 2.4 常用枚举对照

说明：

- JSON 示例中的枚举值保留原始英文，便于后续直接作为契约使用
- 本节用于帮助阅读，不改变实际传输值

`Role（角色）`

- `admin（系统管理员）`
- `executive（高层管理者）`
- `manager（团队负责人）`
- `employee（普通员工）`
- `hr（人力角色）`

`Sensitivity（敏感等级）`

- `public（公开）`
- `internal（内部）`
- `private（私人）`
- `restricted（受限）`

`Actor Type（触发主体类型）`

- `user（用户）`
- `agent（智能体）`
- `system（系统）`

`Approval Status（审批状态）`

- `pending（待审批）`
- `approved（已批准）`
- `rejected（已拒绝）`
- `expired（已过期）`
- `executing（执行中）`
- `executed（已执行成功）`
- `execution_failed（执行失败）`
- `cancelled（已取消）`

`Audit Result（审计结果）`

- `success（成功）`
- `failed（失败）`
- `denied（拒绝）`
- `pending（待处理）`

## 3. API 基础结构

### 3.1 `Api Response Envelope Schema（统一响应包结构）`

```json
{
  "data": {},
  "error": null,
  "meta": {
    "request_id": "req_20260505_001"
  }
}
```

字段定义：

| 字段 | 类型 | 说明 |
| :-- | :-- | :-- |
| `data` | object \| array \| null | 正常返回体 |
| `error` | object \| null | 错误对象 |
| `meta.request_id` | string | 请求链路 ID |

### 3.2 `Api Error Schema（统一错误结构）`

```json
{
  "code": "FORBIDDEN",
  "message": "当前用户无权访问该资源",
  "details": {
    "target_type": "memory",
    "target_id": "mem_001"
  },
  "request_id": "req_20260505_001"
}
```

字段定义：

| 字段 | 类型 | 说明 |
| :-- | :-- | :-- |
| `code` | string | 错误码 |
| `message` | string | 错误说明 |
| `details` | object | 扩展明细 |
| `request_id` | string | 请求链路 ID |

### 3.3 `Pagination Schema（分页结构）`

```json
{
  "page": 1,
  "page_size": 20,
  "total": 100,
  "items": []
}
```

### 3.4 `Auth Token Schema（认证令牌结构）`

```json
{
  "access_token": "jwt_access_token",
  "refresh_token": "jwt_refresh_token",
  "token_type": "Bearer",
  "expires_in": 7200
}
```

### 3.5 `Current User Schema（当前用户结构）`

```json
{
  "user_id": "user_001",
  "org_id": "org_001",
  "team_id": "team_001",
  "role": "manager",
  "display_name": "张三",
  "permissions": [
    "approval:read_team",
    "audit:read_team"
  ]
}
```

## 4. Agent 交互 Schema

### 4.1 `Agent Request Schema（智能体请求结构）`

用途：Dev2 向 Dev1 获取上下文、触发推理、提交动作前的统一请求结构。

```json
{
  "schema_version": "v1",
  "request_id": "req_001",
  "user_id": "user_001",
  "org_id": "org_001",
  "role": "employee",
  "mode_hint": "personal",
  "entry_point": "chat",
  "message": "今天我该做什么",
  "context_hint": {
    "project_id": "proj_001"
  },
  "metadata": {
    "client": "web"
  },
  "created_at": "2026-05-05T10:00:00Z"
}
```

字段定义：

| 字段 | 类型 | 说明 |
| :-- | :-- | :-- |
| `schema_version` | string | 版本号 |
| `request_id` | string | 请求链路 ID |
| `user_id` | string | 当前用户 ID |
| `org_id` | string | 当前组织 ID |
| `role` | string | 当前角色 |
| `mode_hint` | string | 模式提示 |
| `entry_point` | string | 入口，如 `chat/dashboard/project_page` |
| `message` | string | 用户原始输入 |
| `context_hint` | object | 调用方附带的上下文线索 |
| `metadata` | object | 客户端、渠道等扩展信息 |
| `created_at` | datetime | 创建时间 |

### 4.2 `Agent Response Schema（智能体响应结构）`

用途：Dev2 生成结构化结果，Dev3 直接渲染，QA 做行为验证。

```json
{
  "schema_version": "v1",
  "request_id": "req_001",
  "mode": "personal",
  "summary": "今天优先处理登录问题回归和下午评审准备。",
  "facts": [],
  "inferences": [],
  "suggestions": [],
  "sources": [],
  "actions": [],
  "requires_confirmation": false,
  "uncertainty": {
    "level": "low",
    "reason": ""
  },
  "safety": {
    "contains_sensitive_data": false,
    "policy_warnings": []
  }
}
```

### 4.3 `Source Reference Schema（来源引用结构）`

用途：统一描述来源，供 Dev4 提供、Dev2 使用、Dev3 展示。

```json
{
  "schema_version": "v1",
  "source_id": "meeting_001",
  "source_type": "meeting",
  "title": "登录问题复盘会",
  "url": "https://example.com/meeting/001",
  "owner_id": "user_001",
  "timestamp": "2026-05-05T08:00:00Z",
  "permission_scope": "team",
  "sensitivity": "internal"
}
```

### 4.4 `Context Bundle Schema（上下文聚合结构）`

用途：Dev1 / Dev4 将权限过滤后的上下文统一返回给 Dev2。

```json
{
  "schema_version": "v1",
  "request_id": "req_001",
  "mode": "team",
  "user": {},
  "projects": [],
  "tasks": [],
  "meetings": [],
  "memories": [],
  "sources": [],
  "policy": {
    "restricted_filtered": true
  }
}
```

## 5. 核心治理 Schema

### 5.1 `Agent Action Schema（智能体动作结构）`

用途：Dev2 输出结构化动作，Dev1 判断是否审批、如何执行、如何审计。

```json
{
  "schema_version": "v1",
  "id": "act_001",
  "request_id": "req_20260505_001",
  "org_id": "org_001",
  "actor": {
    "type": "agent",
    "user_id": "user_123"
  },
  "action_type": "create_task",
  "title": "创建回归测试任务",
  "description": "为登录模块创建一条 P1 回归测试任务",
  "target": {
    "target_type": "task",
    "target_id": null,
    "system": "agentos"
  },
  "payload": {
    "project_id": "proj_001",
    "assignee_id": "user_456",
    "title": "补充登录回归测试",
    "priority": "high"
  },
  "sources": [
    {
      "schema_version": "v1",
      "source_id": "meeting_001",
      "source_type": "meeting",
      "title": "登录问题复盘会",
      "permission_scope": "team",
      "sensitivity": "internal"
    }
  ],
  "risk_level": "high",
  "sensitivity": "internal",
  "reason": "创建正式任务会影响团队执行计划",
  "requires_approval": true,
  "status": "proposed",
  "created_at": "2026-05-05T10:00:00Z"
}
```

强制字段：

- `schema_version`
- `id`
- `request_id`
- `org_id`
- `actor`
- `action_type`
- `title`
- `target`
- `payload`
- `risk_level`
- `sensitivity`
- `requires_approval`
- `status`
- `created_at`

高风险动作基线：

- 发消息
- 发邮件
- 创建正式任务
- 修改项目状态
- 调用外部系统
- 访问 `private/restricted` 记忆
- 输出正式报告
- 涉及人事、绩效、财务、法务的动作

### 5.2 `Approval Schema（审批结构）`

用途：审批页面、审批状态机和 Agent 提示文案共用。

```json
{
  "schema_version": "v1",
  "id": "approval_001",
  "request_id": "req_20260505_001",
  "org_id": "org_001",
  "requester": {
    "id": "user_123",
    "name": "张三"
  },
  "reviewer": {
    "id": "user_999",
    "name": "李经理"
  },
  "review_policy": "manager_first",
  "status": "pending",
  "risk_level": "high",
  "sensitivity": "internal",
  "title": "创建回归测试任务",
  "description": "Agent 建议创建一条高优先级正式任务",
  "action": {
    "action_id": "act_001",
    "type": "create_task",
    "target_tool": "agentos",
    "target_label": "Task",
    "payload_preview": {
      "project_id": "proj_001",
      "priority": "high"
    }
  },
  "impact": {
    "scope": "team",
    "summary": "影响登录项目排期和任务看板"
  },
  "expires_at": "2026-05-06T10:00:00Z",
  "created_at": "2026-05-05T10:00:00Z",
  "decided_at": null,
  "decision_reason": null
}
```

### 5.3 `Audit Event Schema（审计事件结构）`

用途：统一日志模型，支持安全审计、行为回放、问题排查。

```json
{
  "schema_version": "v1",
  "id": "audit_001",
  "org_id": "org_001",
  "request_id": "req_20260505_001",
  "occurred_at": "2026-05-05T10:00:02Z",
  "actor": {
    "id": "user_123",
    "type": "user"
  },
  "event_type": "request_approval",
  "target_type": "approval",
  "target_id": "approval_001",
  "result": "pending",
  "risk_level": "high",
  "sensitivity": "internal",
  "summary": "Agent 提交创建正式任务请求并进入审批队列",
  "approval_id": "approval_001",
  "details": {
    "action_id": "act_001",
    "action_type": "create_task"
  }
}
```

## 6. 检索与知识 Schema

### 6.1 `Knowledge Search Request Schema（知识检索请求结构）`

```json
{
  "schema_version": "v1",
  "request_id": "req_001",
  "user_id": "user_001",
  "org_id": "org_001",
  "query": "这个客户上次为什么投诉",
  "mode": "knowledge",
  "filters": {
    "project_id": "proj_001",
    "source_type": [
      "meeting",
      "doc"
    ]
  },
  "page": 1,
  "page_size": 10
}
```

### 6.2 `Knowledge Search Response Schema（知识检索响应结构）`

```json
{
  "schema_version": "v1",
  "request_id": "req_001",
  "items": [
    {
      "entity_type": "meeting",
      "entity_id": "meeting_001",
      "title": "客户投诉复盘会",
      "snippet": "客户对交付延迟和升级响应速度不满。",
      "timestamp": "2026-05-03T15:00:00Z",
      "sensitivity": "internal",
      "source": {
        "schema_version": "v1",
        "source_id": "meeting_001",
        "source_type": "meeting",
        "title": "客户投诉复盘会",
        "permission_scope": "team",
        "sensitivity": "internal"
      }
    }
  ],
  "page": 1,
  "page_size": 10,
  "total": 1
}
```

返回约束：

- `restricted` 数据默认不返回正文
- 未授权用户只能拿到过滤后的可见结果
- 每条结果都必须带来源或来源引用

## 7. API 分组定义

### 7.1 `Auth API（认证接口）`

| Method | Path | 说明 | 角色 |
| :-- | :-- | :-- | :-- |
| `POST` | `/api/v1/auth/login` | 登录 | 全部 |
| `POST` | `/api/v1/auth/refresh` | 刷新 token | 全部 |
| `POST` | `/api/v1/auth/logout` | 退出登录 | 全部 |
| `GET` | `/api/v1/me` | 获取当前用户、角色、权限 | 全部 |

### 7.2 `Org and Team API（组织团队接口）`

| Method | Path | 说明 | 角色 |
| :-- | :-- | :-- | :-- |
| `GET` | `/api/v1/orgs/current` | 当前组织信息 | 全部 |
| `GET` | `/api/v1/teams` | 团队列表 | `admin（系统管理员）/executive（高层管理者）/manager（团队负责人）/hr（人力角色）` |
| `POST` | `/api/v1/teams` | 创建团队 | `admin（系统管理员）` |
| `GET` | `/api/v1/users` | 用户列表，按权限过滤 | `admin（系统管理员）/executive（高层管理者）/manager（团队负责人）/hr（人力角色）` |
| `GET` | `/api/v1/users/{id}` | 用户详情 | 按权限 |
| `PATCH` | `/api/v1/users/{id}/role` | 修改角色 | `admin（系统管理员）` |

### 7.3 `Project and Task API（项目任务接口）`

| Method | Path | 说明 | 角色 |
| :-- | :-- | :-- | :-- |
| `GET` | `/api/v1/projects` | 项目列表，支持团队、状态过滤 | 按权限 |
| `POST` | `/api/v1/projects` | 创建项目 | `admin（系统管理员）/executive（高层管理者）/manager（团队负责人）` |
| `GET` | `/api/v1/projects/{id}` | 项目详情 | 按权限 |
| `PATCH` | `/api/v1/projects/{id}` | 更新项目 | `admin（系统管理员）/manager（团队负责人）` |
| `GET` | `/api/v1/tasks` | 任务列表 | 按权限 |
| `POST` | `/api/v1/tasks` | 创建任务 | `admin（系统管理员）/manager（团队负责人）` 或审批执行器 |
| `PATCH` | `/api/v1/tasks/{id}` | 更新任务状态、负责人等 | 按权限 |

### 7.4 `Meeting API（会议接口）`

| Method | Path | 说明 | 角色 |
| :-- | :-- | :-- | :-- |
| `GET` | `/api/v1/meetings` | 会议列表 | 按权限 |
| `GET` | `/api/v1/meetings/{id}` | 会议详情，返回脱敏结果 | 按权限 |
| `POST` | `/api/v1/meetings/import` | Connector 导入会议 | `admin（系统管理员）/system（系统）` |

### 7.5 `Memory API（记忆接口）`

| Method | Path | 说明 | 角色 |
| :-- | :-- | :-- | :-- |
| `GET` | `/api/v1/memory` | 记忆列表，支持状态、所有者、范围过滤 | 按权限 |
| `GET` | `/api/v1/memory/{id}` | 记忆详情 | 按权限 |
| `POST` | `/api/v1/memory` | 创建记忆 | 本人或系统 |
| `PATCH` | `/api/v1/memory/{id}` | 更新记忆 | 所有者 / 授权管理者 |
| `PATCH` | `/api/v1/memory/{id}/archive` | 归档记忆 | 所有者 / 授权管理者 |
| `DELETE` | `/api/v1/memory/{id}` | 软删除记忆 | 所有者 / `admin（系统管理员）` |

返回约束：

- 默认不返回 `deleted`
- `restricted` 默认不返回正文，只返回占位和申请访问提示
- 查询他人记忆时默认只返回授权可见的摘要字段

### 7.6 `Approval API（审批接口）`

| Method | Path | 说明 | 角色 |
| :-- | :-- | :-- | :-- |
| `GET` | `/api/v1/approvals` | 审批队列 | 按权限 |
| `GET` | `/api/v1/approvals/{id}` | 审批详情 | 审批人 / 发起人 / `admin（系统管理员）` |
| `POST` | `/api/v1/approvals` | 创建审批项 | `agent（智能体）/system（系统）` |
| `POST` | `/api/v1/approvals/{id}/approve` | 批准 | 审批人 |
| `POST` | `/api/v1/approvals/{id}/reject` | 拒绝 | 审批人 |
| `POST` | `/api/v1/approvals/{id}/cancel` | 撤销待审批项 | 发起人 / `admin（系统管理员）` |

### 7.7 `Audit API（审计接口）`

| Method | Path | 说明 | 角色 |
| :-- | :-- | :-- | :-- |
| `GET` | `/api/v1/audit` | 审计查询 | 按权限 |
| `GET` | `/api/v1/audit/{id}` | 审计详情 | 按权限 |

查询参数建议：

```text
from, to, actor_id, event_type, risk_level, target_type, target_id, page, page_size
```

### 7.8 `Agent Action API（智能体动作接口）`

| Method | Path | 说明 | 调用方 |
| :-- | :-- | :-- | :-- |
| `POST` | `/api/v1/agent/actions` | 提交动作 | Dev2 |
| `POST` | `/api/v1/agent/actions/{id}/evaluate` | 风险判断与审批判定 | Dev2 / Server |
| `POST` | `/api/v1/agent/actions/{id}/execute` | 执行动作 | Server |

### 7.9 `Context API（上下文接口）`

| Method | Path | 说明 | 调用方 |
| :-- | :-- | :-- | :-- |
| `GET` | `/api/v1/context` | 按模式获取上下文 | Dev2 |

### 7.10 `Knowledge Search API（知识检索接口）`

| Method | Path | 说明 | 调用方 |
| :-- | :-- | :-- | :-- |
| `POST` | `/api/v1/knowledge/search` | 聚合检索 | Dev2 / Dev3 |
| `GET` | `/api/v1/knowledge/aggregate` | 知识聚合回答 | 按权限 |

### 7.11 `Connector API（连接器接口）`

| Method | Path | 说明 | 角色 |
| :-- | :-- | :-- | :-- |
| `GET` | `/api/v1/connectors` | 来源列表 | `admin（系统管理员）` |
| `POST` | `/api/v1/connectors` | 新增来源 | `admin（系统管理员）` |
| `PATCH` | `/api/v1/connectors/{id}` | 更新来源配置 | `admin（系统管理员）` |
| `POST` | `/api/v1/connectors/{id}/sync` | 触发同步 | `admin（系统管理员）/system（系统）` |
| `GET` | `/api/v1/connectors/{id}/sync-status` | 查看同步状态 | `admin（系统管理员）` |

### 7.12 `Business Aggregation API（业务聚合接口）`

| Method | Path | 说明 | 角色 |
| :-- | :-- | :-- | :-- |
| `GET` | `/api/v1/dashboard/management-brief` | 管理层组织简报 | `executive（高层管理者）/admin（系统管理员）` |
| `GET` | `/api/v1/projects/{id}/status-assistant` | 项目状态助手 | `manager（团队负责人）/executive（高层管理者）/admin（系统管理员）` |
| `GET` | `/api/v1/personal-brief` | 个人每日简报 | `employee（普通员工）/manager（团队负责人）/executive（高层管理者）/admin（系统管理员）` |

## 8. 错误码建议

| Code | 场景 |
| :-- | :-- |
| `UNAUTHORIZED` | 未登录或 token 无效 |
| `FORBIDDEN` | 无权限 |
| `RESTRICTED_RESOURCE` | 访问 restricted 资源 |
| `APPROVAL_REQUIRED` | 高风险动作需要审批 |
| `APPROVAL_EXPIRED` | 审批已过期 |
| `VALIDATION_ERROR` | 参数错误 |
| `NOT_FOUND` | 资源不存在 |
| `CONFLICT` | 并发更新冲突 |
| `INTERNAL_ERROR` | 服务内部错误 |

## 9. 审批状态流转

```text
pending -> approved -> executing -> executed
pending -> rejected
pending -> expired
approved -> execution_failed
pending -> cancelled
```

状态说明：

- `pending`：待审批
- `approved`：已批准，等待执行
- `rejected`：已拒绝
- `expired`：超时过期
- `executing`：执行中
- `executed`：执行成功
- `execution_failed`：执行失败
- `cancelled`：发起人撤销

触发规则：

- Agent 提交高风险动作时创建 `pending`
- 审批人通过时转 `approved`
- 执行器领取时转 `executing`
- 执行成功时转 `executed`
- 执行异常时转 `execution_failed`
- 超过 `expires_at` 且未处理时转 `expired`
- 发起人在未审批前可转 `cancelled`

## 10. 审计事件枚举

```text
read_source（读取来源）
read_memory（读取记忆）
read_restricted_attempt（尝试读取受限内容）
generate_output（生成输出）
submit_agent_action（提交智能体动作）
request_approval（发起审批）
approve_action（批准动作）
reject_action（拒绝动作）
expire_approval（审批过期）
cancel_approval（取消审批）
execute_action（执行动作）
execution_failed（执行失败）
update_project（更新项目）
create_task（创建任务）
update_memory（更新记忆）
archive_memory（归档记忆）
delete_memory（删除记忆）
break_glass_request（发起受控访问申请）
break_glass_grant（授予受控访问）
break_glass_expire（受控访问过期）
permission_denied（权限拒绝）
connector_sync（连接器同步）
connector_sync_failed（连接器同步失败）
```

审计落库原则：

- 审计日志只追加，不原地修改
- 审批结果通过新增事件体现，不覆盖 `request_approval`
- 对越权访问也要落审计
- 对敏感读取尝试无论成功失败都要落审计

## 11. 结论

本文档是 Dev1 对外联调和冻结 Schema 的事实契约文档。后续如果出现以下变更，应优先更新本文档：

- API 路径调整
- 请求或响应结构调整
- 共享 Schema 字段调整
- 错误结构或分页结构调整
- 审批状态机调整
- 审计事件枚举调整
