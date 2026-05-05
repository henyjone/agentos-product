# Dev4 外部系统通用接口规范 v1（含 Git/飞书示例动作清单）

## 1. 文档目标

本文档定义 Dev4 对外部系统接入的统一规范，目标是让 Dev1、Dev2、Dev3、QA 围绕同一套“可治理、可审计、可扩展”的连接器契约工作。

适用场景：

- Git 仓库操作（如建仓、拉取、推送、删仓）
- 飞书操作（如发消息、创建日程、创建文档）
- 未来扩展到 Jira、Notion、邮件、CRM 等

## 2. 角色与责任边界

### 2.1 责任分工

- `Dev2（Agent）`：理解用户意图，生成动作提案（Agent Action），不直接调用外部系统。
- `Dev1（Control Plane）`：风险评估、权限校验、审批流、执行调度、审计落库。
- `Dev4（Connector Plane）`：实现外部系统连接器、执行适配、结果标准化返回。

### 2.2 执行原则

- 所有“代表用户执行”的外部写操作，默认由 Dev1 发起调用 Dev4 执行。
- Dev4 不承担审批决策，不绕过 Dev1 直接执行高风险动作。
- Dev4 可以执行只读同步任务（系统任务），但必须写审计事件。

## 3. 总体执行流程

```text
User Request
-> Dev2 生成 Agent Action（proposed）
-> Dev1 风险评估 + 权限校验
-> (需要审批) Approval pending -> approved
-> Dev1 调用 Dev4 Connector Execute API
-> Dev4 调用外部系统
-> Dev4 返回标准结果
-> Dev1 更新 Action/Approval 状态并写 Audit
```

## 4. 通用动作模型

### 4.1 Action Catalog（动作目录）结构

每个外部动作必须在目录中注册，最小字段：

```json
{
  "action_key": "git.repo.create",
  "provider": "gitea",
  "category": "write",
  "risk_level": "high",
  "requires_approval": true,
  "required_permissions": [
    "connector:git:repo:create"
  ],
  "idempotency": "conditional",
  "dry_run_supported": true,
  "input_schema_ref": "schema://git.repo.create.input.v1",
  "output_schema_ref": "schema://git.repo.create.output.v1",
  "timeout_seconds": 30,
  "retry_policy": {
    "max_retries": 2,
    "retryable_errors": [
      "CONNECTOR_TIMEOUT",
      "PROVIDER_5XX"
    ]
  }
}
```

字段定义：

| 字段 | 类型 | 必填 | 说明 | 可选值/示例 |
| :-- | :-- | :-- | :-- | :-- |
| `action_key` | string | Y | 动作唯一标识，`<domain>.<resource>.<verb>` | `git.repo.create` |
| `provider` | string | Y | 连接器提供方 | `gitea/github/feishu` |
| `category` | string | Y | 动作类别 | `read/write/admin` |
| `risk_level` | string | Y | 风险等级 | `low/medium/high/critical` |
| `requires_approval` | boolean | Y | 是否默认需要审批 | `true` |
| `required_permissions` | string[] | Y | 执行所需权限点 | `connector:git:repo:create` |
| `idempotency` | string | Y | 幂等策略 | `none/strict/conditional` |
| `dry_run_supported` | boolean | Y | 是否支持预演 | `true` |
| `input_schema_ref` | string | Y | 入参 schema 引用 | `schema://git.repo.create.input.v1` |
| `output_schema_ref` | string | Y | 出参 schema 引用 | `schema://git.repo.create.output.v1` |
| `timeout_seconds` | integer | Y | 超时时间（秒） | `30` |
| `retry_policy.max_retries` | integer | Y | 最大重试次数 | `2` |
| `retry_policy.retryable_errors` | string[] | Y | 可重试错误码 | `CONNECTOR_TIMEOUT` |

### 4.2 `action_key` 命名与行为类型

命名格式：

```text
<系统域>.<资源对象>.<行为动词>
```

示例：

- `git.repo.create`
- `git.branch.list`
- `git.member.remove`
- `feishu.message.send`
- `feishu.doc.update`

行为动词（第三段）建议分层：

- `read（读取类）`：`list/get/search/export`
- `write（写入类）`：`create/update/send/sync/commit`
- `admin（管理类）`：`delete/archive/grant/revoke/transfer`

建议做法：

- 同一资源的高风险动作尽量落在 `admin` 行为层
- `delete/grant/revoke` 默认评估为 `high` 或 `critical`

### 4.3 风险等级定义

- `low（低风险）`：只读、无状态变更。
- `medium（中风险）`：低影响写操作，可按策略审批。
- `high（高风险）`：会影响项目流程或多人协作，默认审批。
- `critical（关键风险）`：破坏性或不可逆操作，强审批或默认禁用。

## 5. Dev4 通用接口规范

## 5.1 Connector Metadata API（连接器元信息接口）

用于 Dev1 查询某连接器支持哪些动作。

- `GET /internal/v1/connectors/{provider}/capabilities`

返回示例：

```json
{
  "provider": "gitea",
  "version": "v1",
  "actions": [
    "git.repo.get",
    "git.repo.create",
    "git.repo.delete"
  ]
}
```

## 5.2 Connector Execute API（连接器执行接口）

由 Dev1 调用，Dev4 执行外部动作。

- `POST /internal/v1/connectors/execute`

请求示例：

```json
{
  "request_id": "req_001",
  "action_id": "act_001",
  "action_key": "git.repo.create",
  "provider": "gitea",
  "org_id": "org_001",
  "operator": {
    "user_id": "user_001",
    "role": "manager"
  },
  "approval_context": {
    "required": true,
    "approval_id": "approval_001",
    "status": "approved"
  },
  "dry_run": false,
  "payload": {
    "owner": "team-a",
    "repo_name": "agentos-demo",
    "private": true
  },
  "idempotency_key": "act_001_v1"
}
```

请求字段定义：

| 字段 | 类型 | 必填 | 说明 | 可选值/示例 |
| :-- | :-- | :-- | :-- | :-- |
| `request_id` | string | Y | 请求链路 ID | `req_001` |
| `action_id` | string | Y | 对应 AgentAction ID | `act_001` |
| `action_key` | string | Y | 具体执行动作 | `git.repo.create` |
| `provider` | string | Y | 目标连接器 | `gitea` |
| `org_id` | string(UUID) | Y | 组织 ID | `org_001` |
| `operator.user_id` | string(UUID) | Y | 操作人 ID | `user_001` |
| `operator.role` | string | Y | 操作人角色 | `admin/executive/manager/employee/hr` |
| `approval_context.required` | boolean | Y | 是否要求审批 | `true` |
| `approval_context.approval_id` | string | N | 审批单 ID，要求审批时必填 | `approval_001` |
| `approval_context.status` | string | N | 审批状态，要求审批时必填 | `approved` |
| `dry_run` | boolean | Y | 仅预演不落外部状态 | `false` |
| `payload` | object | Y | 动作参数体 | 见动作 input schema |
| `idempotency_key` | string | Y(写操作) | 幂等键，防重复执行 | `act_001_v1` |

响应示例：

```json
{
  "request_id": "req_001",
  "action_id": "act_001",
  "provider_request_id": "gitea_req_7788",
  "status": "success",
  "result": {
    "repo_id": "12345",
    "repo_url": "https://git.example.com/team-a/agentos-demo"
  },
  "error": null,
  "started_at": "2026-05-05T10:00:00Z",
  "finished_at": "2026-05-05T10:00:02Z"
}
```

响应字段定义：

| 字段 | 类型 | 必填 | 说明 | 可选值/示例 |
| :-- | :-- | :-- | :-- | :-- |
| `request_id` | string | Y | 请求链路 ID | `req_001` |
| `action_id` | string | Y | 动作 ID | `act_001` |
| `provider_request_id` | string | N | 外部系统请求 ID | `gitea_req_7788` |
| `status` | string | Y | 执行结果状态 | `success/failed/pending` |
| `result` | object \| null | N | 成功结果体 | `repo_id/repo_url` |
| `error` | object \| null | N | 失败错误体 | `{code,message,details}` |
| `started_at` | string(datetime) | Y | 执行开始时间 | `2026-05-05T10:00:00Z` |
| `finished_at` | string(datetime) | N | 执行结束时间 | `2026-05-05T10:00:02Z` |

`error` 子字段：

- `code`：标准错误码（见第 6 节）
- `message`：错误描述
- `details`：外部系统返回上下文（可脱敏）

## 5.3 Connector Validate API（参数校验接口，可选）

- `POST /internal/v1/connectors/validate`

用于执行前参数预校验和权限预检查，支持 Dev1 在审批前给用户展示更精确的执行预览。

建议入参：

- `action_key`
- `provider`
- `operator`
- `payload`
- `dry_run`

建议返回：

- `valid`（boolean）
- `errors`（array）
- `warnings`（array）
- `normalized_payload`（object，可选）

## 6. 通用错误码

| Code | 含义 |
| :-- | :-- |
| `CONNECTOR_NOT_FOUND` | 连接器不存在 |
| `ACTION_NOT_SUPPORTED` | 连接器不支持该动作 |
| `PAYLOAD_INVALID` | 参数不合法 |
| `APPROVAL_REQUIRED` | 缺少审批上下文 |
| `APPROVAL_INVALID` | 审批状态不满足执行条件 |
| `PERMISSION_DENIED` | 权限不足 |
| `PROVIDER_AUTH_FAILED` | 外部系统认证失败 |
| `PROVIDER_RATE_LIMIT` | 外部系统限流 |
| `PROVIDER_4XX` | 外部系统业务错误 |
| `PROVIDER_5XX` | 外部系统服务错误 |
| `CONNECTOR_TIMEOUT` | 连接器超时 |
| `IDEMPOTENCY_CONFLICT` | 幂等键冲突 |
| `INTERNAL_ERROR` | 连接器内部错误 |

## 7. 幂等、重试与超时

- 写操作必须提供 `idempotency_key`，避免重复执行。
- Dev4 只对“明确可重试”的错误重试。
- 默认超时建议：
- Git：30 秒
- 飞书消息：10 秒
- 飞书文档创建：20 秒
- Dev4 返回的 `provider_request_id` 必须可追溯，用于定位外部系统请求。

## 8. 审计要求

每次执行必须返回以下审计关键信息给 Dev1：

- `request_id`
- `action_id`
- `action_key`
- `provider`
- `operator.user_id`
- `approval_id`（如有）
- `status`
- `provider_request_id`
- `started_at` / `finished_at`
- `error.code` / `error.message`（失败时）

## 9. 安全与权限要求

- Dev4 不信任调用方，必须验证来自 Dev1 的服务身份。
- 外部系统凭证采用最小权限原则，按组织隔离管理。
- `critical` 动作建议在 Dev4 侧再做一层硬保护（例如默认禁删仓）。
- 敏感返回字段必须脱敏。

## 10. Git 示例动作清单（v1）

## 10.1 Read（读）

- `git.repo.list（仓库列表）`
- `git.repo.get（仓库详情）`
- `git.branch.list（分支列表）`
- `git.commit.list（提交列表）`
- `git.mr.list（合并请求列表）`

## 10.2 Write（写）

- `git.branch.create（创建分支）`
- `git.file.commit（提交文件变更）`
- `git.mr.create（创建合并请求）`
- `git.tag.create（创建标签）`

## 10.3 Admin（管理/高风险）

- `git.repo.create（创建仓库）` -> `high`
- `git.repo.archive（归档仓库）` -> `high`
- `git.repo.delete（删除仓库）` -> `critical`
- `git.member.add（添加成员）` -> `high`
- `git.member.remove（移除成员）` -> `high`

## 11. 飞书示例动作清单（v1）

## 11.1 Read（读）

- `feishu.user.get（获取用户信息）`
- `feishu.chat.get（获取会话信息）`
- `feishu.calendar.list（查询日程）`

## 11.2 Write（写）

- `feishu.message.send（发送消息）` -> `high`
- `feishu.calendar.create_event（创建日程）` -> `medium/high`（按策略）
- `feishu.doc.create（创建文档）` -> `medium`
- `feishu.doc.update（更新文档）` -> `medium`

## 11.3 Admin（管理/高风险）

- `feishu.chat.member.add（拉人入群）` -> `high`
- `feishu.chat.member.remove（移出群）` -> `high`
- `feishu.permission.grant（授权提升）` -> `critical`

## 12. 最小落地清单（MVP）

- 定义 `Action Catalog` 注册机制
- 落地 `Connector Execute API`
- 落地 Git 连接器（至少 6 个动作，含 2 个高风险动作）
- 落地飞书连接器（至少 4 个动作，含 1 个高风险动作）
- 完成 Dev1 审批联调（高风险动作必须审批）
- 完成审计联调（每次执行可追溯）
- 完成 QA 用例（越权、无审批、重试、超时、幂等）

## 13. 验收标准

- Dev1 可基于统一接口调用不同外部系统动作，无需改核心编排逻辑
- 高风险动作在未审批时无法执行
- 每个执行动作都可追溯到 `action_id + provider_request_id`
- Git 与飞书最小动作清单可在同一流程跑通
- 新接入第三方系统只需实现同一连接器规范，不破坏既有契约
