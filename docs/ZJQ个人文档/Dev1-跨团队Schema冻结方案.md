# AgentOS Dev1 跨团队 Schema 冻结方案（Java 版）

## 1. 文档目的

本文档用于把以下文档正式对齐，并补齐可直接执行的冻结清单：

- `docs/development-plans/dev1-backend-tech-lead.md`
- `docs/ZJQ个人文档/AgentOS服务设计方案.md`
- `docs/ZJQ个人文档/AgentOS数据库模型定义.md`
- `docs/ZJQ个人文档/AgentOS接口契约与Schema定义.md`

本文档的目标不是重复所有设计细节，而是明确以下内容：

1. Dev1 后端技术路线正式采用 `Java`
2. 哪些内容已经对齐
3. 哪些内容仍有缺口，需要补齐后才能联调
4. 哪些跨团队 Schema 需要冻结
5. 冻结后的命名、字段、版本和变更规则是什么

适用角色：

- Dev1：后端 / Tech Lead / Workflow
- Dev2：AI / Agent Engineer
- Dev3：Frontend / Product Engineer
- Dev4：Integrations / Data / Knowledge Engineer
- QA：测试 / 安全 / 权限验证

## 2. 本次对齐结论

### 2.1 技术选型结论

Dev1 后端正式采用以下技术栈：

- Web 框架：`Spring Boot 3.x`
- 安全框架：`Spring Security`
- 数据访问：`Spring Data JPA` 或 `MyBatis`
- 数据库：`PostgreSQL 16+`
- 缓存 / 队列：`Redis`
- 异步任务：`Spring Scheduler` + `Spring Async`，复杂场景可扩展消息队列
- 数据迁移：`Flyway`
- API 契约：`OpenAPI 3.x`
- 认证：`JWT + Refresh Token`
- 对象存储(暂不考虑)：`MinIO` 或 `S3`
- 检索：`PostgreSQL GIN + pgvector`

说明：

- `AgentOS服务设计方案.md` 中原有 `FastAPI + Alembic + Celery` 表述，现统一替换为 Java 技术路线理解。
- Dev2 的 `agent_engine` 继续保留 `Python`，通过 HTTP/OpenAPI 与 Dev1 后端交互，不强行统一语言。

### 2.2 已对齐内容

以下内容在两份上游文档中已经基本一致，可以直接作为冻结输入：

- Dev1 负责系统骨架、数据库、API、权限、审批、审计和 Workflow Engine
- 核心领域对象包括 `Org/User/Team/Project/Task/Meeting/Memory/Approval/AuditEvent/ConnectorSource`
- 角色模型包括 `Admin/Executive/Manager/Employee/HR`
- 数据敏感等级包括 `public/internal/private/restricted`
- 高风险动作必须先审批，再执行
- 关键读取、审批、执行都必须审计
- MVP 必须提供审批 API、审计 API、Memory API 和业务聚合 API

### 2.3 当前缺口

在本轮文档拆分前，虽然主线一致，但要真正“冻结跨团队 Schema”，还缺以下内容：

1. 技术栈未切换到 Java 版本表述
2. 目前只显式冻结了三类共享 Schema，范围偏小
3. `AgentRequest`、`AgentResponse`、`SourceReference`、`ContextBundle` 等跨团队对象还未正式冻结
4. 字段命名规则、时间格式、ID 规则、枚举规范还未统一
5. API 契约缺少版本治理规则
6. Schema 缺少“谁负责、谁消费、何时可改”的治理说明
7. 缺少联调前必须完成的冻结清单和验收标准

## 3. 冻结跨团队 Schema 的定义

“冻结跨团队 Schema” 的意思是：

- 先把所有跨团队共享的数据结构定义成 `v1`
- 在联调开始前，字段名、字段类型、枚举值、必填项、语义保持稳定
- Dev1、Dev2、Dev3、Dev4、QA 都按同一版契约开发
- 任何变更不能口头修改，必须更新文档、变更记录和版本号

冻结不等于永远不改，而是：

- `v1` 冻结后只允许兼容性新增
- 非兼容修改必须升级版本，例如 `v2`
- 未冻结字段不能被当作跨团队依赖前提

## 4. 冻结范围

本次建议冻结范围分为三层。

### 4.1 第一层：必须冻结的共享领域对象

- `Org Schema（组织结构）`
- `User Schema（用户结构）`
- `Team Schema（团队结构）`
- `Project Schema（项目结构）`
- `Task Schema（任务结构）`
- `Meeting Schema（会议结构）`
- `Memory Schema（记忆结构）`
- `ConnectorSource Schema（数据来源结构）`
- `Approval Schema（审批结构）`
- `Audit Event Schema（审计事件结构）`

### 4.2 第二层：必须冻结的 Agent 交互对象

- `Agent Request Schema（智能体请求结构）`
- `Agent Response Schema（智能体响应结构）`
- `Agent Action Schema（智能体动作结构）`
- `Source Reference Schema（来源引用结构）`
- `Context Bundle Schema（上下文聚合结构）`
- `Knowledge Search Request Schema（知识检索请求结构）`
- `Knowledge Search Response Schema（知识检索响应结构）`

### 4.3 第三层：必须冻结的 API 包装对象

- `Api Response Envelope Schema（统一响应包结构）`
- `Api Error Schema（统一错误结构）`
- `Pagination Schema（分页结构）`
- `Auth Token Schema（认证令牌结构）`
- `Current User Schema（当前用户结构）`

## 5. 冻结原则

### 5.1 命名原则

- JSON 字段统一使用 `snake_case`
- 枚举值统一使用小写英文，必要时使用下划线，如 `pending_approval`
- 布尔字段统一使用 `is_` 或明确语义，如 `requires_approval`
- 时间字段统一以 `_at` 结尾，如 `created_at`
- ID 字段统一以 `_id` 结尾，如 `user_id`、`approval_id`

### 5.2 类型原则

- 主键统一使用 `UUID` 字符串
- 时间统一使用 `ISO-8601 UTC`，例如 `2026-05-05T10:00:00Z`
- 金额、分数、权重如无特殊需要，MVP 不单独引入复杂类型
- 可扩展字段统一放在 `metadata` 或 `details` 中，不能随意塞入顶层

### 5.3 权限原则

- 任何 Schema 如果涉及敏感数据，必须带 `sensitivity`
- 任何跨来源数据，必须带 `source` 或 `source_refs`
- 任何可见性受限对象，必须带 `visibility_scope` 或同等语义字段
- `restricted` 内容默认不可直接下发正文

### 5.4 兼容原则

- 已冻结字段不能随意改名
- 已冻结枚举不能随意删除
- 可以新增可选字段
- 新增必填字段必须升级版本

## 6. 冻结清单总表

| 类别       | 英文名 + 中文                                     | 状态   | 负责人                | 消费方               | 备注          |
| :------- | :------------------------------------------- | :--- | :----------------- | :---------------- | :---------- |
| 核心实体     | `Org Schema（组织结构）`                           | 待冻结  | Dev1               | Dev2/Dev3/Dev4/QA | 已有草案        |
| 核心实体     | `User Schema（用户结构）`                          | 待冻结  | Dev1               | Dev2/Dev3/Dev4/QA | 已有草案        |
| 核心实体     | `Team Schema（团队结构）`                          | 待冻结  | Dev1               | Dev2/Dev3/Dev4/QA | 已有草案        |
| 核心实体     | `Project Schema（项目结构）`                       | 待冻结  | Dev1               | Dev2/Dev3/Dev4/QA | 已有草案        |
| 核心实体     | `Task Schema（任务结构）`                          | 待冻结  | Dev1               | Dev2/Dev3/Dev4/QA | 已有草案        |
| 核心实体     | `Meeting Schema（会议结构）`                       | 待冻结  | Dev1               | Dev2/Dev3/Dev4/QA | 已有草案        |
| 核心实体     | `Memory Schema（记忆结构）`                        | 待冻结  | Dev1               | Dev2/Dev3/Dev4/QA | 已有草案        |
| 核心实体     | `ConnectorSource Schema（数据来源结构）`             | 待冻结  | Dev1               | Dev2/Dev3/Dev4/QA | 已有草案        |
| 核心闭环     | `Agent Action Schema（智能体动作结构）`               | 待冻结  | Dev1 + Dev2        | Dev3/QA           | 已有草案，需补版本治理 |
| 核心闭环     | `Approval Schema（审批结构）`                      | 待冻结  | Dev1               | Dev2/Dev3/QA      | 已有草案        |
| 核心闭环     | `Audit Event Schema（审计事件结构）`                 | 待冻结  | Dev1               | Dev3/QA           | 已有草案        |
| Agent 交互 | `Agent Request Schema（智能体请求结构）`              | 已补齐  | Dev1 + Dev2        | Dev3/QA           | 已落到接口文档     |
| Agent 交互 | `Agent Response Schema（智能体响应结构）`             | 已补齐  | Dev1 + Dev2 + Dev3 | QA                | 已落到接口文档     |
| Agent 交互 | `Source Reference Schema（来源引用结构）`             | 已补齐  | Dev1 + Dev4        | Dev2/Dev3/QA      | 已落到接口文档     |
| Agent 交互 | `Context Bundle Schema（上下文聚合结构）`              | 已补齐  | Dev1 + Dev4        | Dev2              | 已落到接口文档     |
| 检索       | `Knowledge Search Request Schema（知识检索请求结构）`  | 已补齐  | Dev1 + Dev4        | Dev2/Dev3         | 已落到接口文档     |
| 检索       | `Knowledge Search Response Schema（知识检索响应结构）` | 已补齐  | Dev1 + Dev4        | Dev2/Dev3/QA      | 已落到接口文档     |
| API 基础   | `Api Response Envelope Schema（统一响应包结构）`      | 已补齐  | Dev1               | 全部                | 已落到接口文档     |
| API 基础   | `Api Error Schema（统一错误结构）`                | 已补齐  | Dev1               | 全部                | 已落到接口文档     |
| API 基础   | `Pagination Schema（分页结构）`                 | 已补齐  | Dev1               | Dev3/QA           | 已落到接口文档     |
| API 基础   | `Auth Token Schema（认证令牌结构）`               | 已补齐  | Dev1               | Dev3              | 已落到接口文档     |
| API 基础   | `Current User Schema（当前用户结构）`             | 已补齐  | Dev1               | Dev2/Dev3         | 已落到接口文档     |

## 7. 已有内容与缺口补齐

### 7.1 已有三类共享 Schema 可以保留

`AgentOS服务设计方案.md` 中以下三类对象已具备冻结基础：

- `Agent Action Schema（智能体动作结构）`
- `Approval Schema（审批结构）`
- `Audit Event Schema（审计事件结构）`

这些内容建议保留为主干，不推倒重写。

### 7.2 必须新增的四类共享 Schema

为了让 Dev2、Dev3、Dev4 真正能联调，仅冻结上面三类还不够，还必须新增以下对象。

#### A. `Agent Request Schema（智能体请求结构）`

用途：

- Dev2 向 Dev1 获取上下文、触发推理、提交动作前的统一入口

建议最小字段：

```json
{
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

#### B. `Agent Response Schema（智能体响应结构）`

用途：

- Dev2 产出结构化结果
- Dev3 直接渲染
- QA 校验模式、来源、动作、确认要求是否完整

建议最小字段：

```json
{
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

#### C. `Source Reference Schema（来源引用结构）`

用途：

- Dev4 提供可追溯来源
- Dev2 做带出处回答
- Dev3 展示来源信息

建议最小字段：

```json
{
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

#### D. `Context Bundle Schema（上下文聚合结构）`

用途：

- Dev1 / Dev4 把权限过滤后的上下文统一返回给 Dev2

建议最小字段：

```json
{
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

## 8. 三类核心共享 Schema 的补强要求

### 8.1 `Agent Action Schema（智能体动作结构）`

当前已定义，但还需要补强：

- 增加 `schema_version`
- 明确 `actor.type` 枚举：`user/agent/system`
- 明确 `target.system` 枚举
- 明确 `status` 是否与审批状态严格解耦
- 明确 `payload` 中哪些字段可直接执行，哪些只是预览
- 明确 `sources` 使用统一的 `Source Reference Schema（来源引用结构）`

建议强制字段：

- `id`
- `schema_version`
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

### 8.2 `Approval Schema（审批结构）`

当前已定义，但还需要补强：

- 增加 `schema_version`
- 增加 `request_id`
- 增加 `org_id`
- 增加 `review_policy`
- 明确 `reviewer` 为空时的指派规则
- 明确 `impact.scope` 枚举
- 明确 `payload_preview` 的脱敏规则

### 8.3 `Audit Event Schema（审计事件结构）`

当前已定义，但还需要补强：

- 增加 `schema_version`
- 增加 `org_id` 到示例 JSON
- 明确 `details` 最大范围，防止写入敏感原文
- 明确 `event_type` 与业务动作的边界
- 明确成功、失败、拒绝、待审批的判定规则

## 9. API 契约冻结要求

除了对象 Schema，API 契约也必须同步冻结。

### 9.1 必须冻结的接口组

- `Auth API（认证接口）`
- `Current User API（当前用户接口）`
- `Org and Team API（组织团队接口）`
- `Project and Task API（项目任务接口）`
- `Meeting API（会议接口）`
- `Memory API（记忆接口）`
- `Approval API（审批接口）`
- `Audit API（审计接口）`
- `Agent Action API（智能体动作接口）`
- `Context API（上下文接口）`
- `Knowledge Search API（知识检索接口）`
- `Connector API（连接器接口）`
- `Management Brief API（管理简报接口）`
- `Project Status API（项目状态接口）`
- `Personal Brief API（个人简报接口）`

### 9.2 API 统一规则

- 路径统一使用 `/api/v1/...`
- 成功响应统一返回 `data + error + meta`
- 所有响应都返回 `request_id`
- 分页接口统一返回 `page/page_size/total/items`
- 错误响应统一包含 `code/message/details/request_id`
- 路径参数风格统一采用 OpenAPI 风格，如 `/users/{id}`，不使用混写风格

## 10. 版本与变更治理

### 10.1 版本字段要求

以下共享对象必须携带 `schema_version`：

- `Agent Action Schema（智能体动作结构）`
- `Approval Schema（审批结构）`
- `Audit Event Schema（审计事件结构）`
- `Agent Request Schema（智能体请求结构）`
- `Agent Response Schema（智能体响应结构）`
- `Context Bundle Schema（上下文聚合结构）`
- `Knowledge Search Response Schema（知识检索响应结构）`

建议首版统一使用：

```text
schema_version = "v1"
```

### 10.2 变更规则

- 新增可选字段：允许，需更新文档
- 新增必填字段：不允许直接改，需升版本
- 字段改名：不允许直接改，需升版本
- 枚举删除：不允许直接改，需升版本
- 枚举新增：允许，但需通知消费方和 QA

### 10.3 责任归属

- Dev1：最终契约 owner，负责 OpenAPI 和服务 DTO
- Dev2：确认 Agent 请求、响应、动作结构可生产
- Dev3：确认前端可渲染、字段语义清晰
- Dev4：确认来源、权限、敏感等级字段可稳定提供
- QA：确认可基于冻结契约编写接口、权限、审计测试

## 11. 冻结前必须完成的查漏补缺清单

### P0

- [x] 将 `AgentOS服务设计方案.md` 的技术栈表述改为 Java 版
- [x] 增补 `Agent Request Schema（智能体请求结构）`
- [x] 增补 `Agent Response Schema（智能体响应结构）`
- [x] 增补 `Source Reference Schema（来源引用结构）`
- [x] 增补 `Context Bundle Schema（上下文聚合结构）`
- [x] 增补 `Knowledge Search Request Schema（知识检索请求结构）`
- [x] 增补 `Knowledge Search Response Schema（知识检索响应结构）`
- [x] 增补 `Api Error Schema（统一错误结构）`
- [x] 增补 `Pagination Schema（分页结构）`
- [x] 为核心共享 Schema 增加 `schema_version`
- [x] 统一路径参数风格为 OpenAPI 风格

### P1

- [ ] 产出 `OpenAPI v1` 草案
- [ ] 产出 Java DTO 命名草案
- [ ] 明确 `Agent Action -> Approval -> Audit Event` 字段映射关系
- [ ] 明确 `restricted` 内容的返回占位格式
- [ ] 明确前端审批页最小展示字段

### P2

- [ ] 产出联调 mock JSON
- [ ] 产出 QA 契约测试样例
- [ ] 产出错误码与权限拒绝样例

## 12. 冻结验收标准

当以下条件同时满足时，认为 `Schema v1` 可以冻结：

1. Dev1 可以基于冻结清单生成 Java DTO 和 OpenAPI 文档
2. Dev2 可以稳定提交 `Agent Action Schema（智能体动作结构）`
3. Dev2 可以稳定消费 `Context Bundle Schema（上下文聚合结构）`
4. Dev3 可以渲染 `Agent Response Schema（智能体响应结构）`、审批页和审计页
5. Dev4 可以稳定返回 `Source Reference Schema（来源引用结构）` 和检索结果
6. QA 可以基于冻结后的字段、枚举和值域写接口测试和权限测试
7. 冻结后的样例 JSON 已存档，联调不再口头解释字段

## 13. Dev1 下一步落地建议

建议按以下顺序推进：

1. 先以本文档为基准，评审并冻结 `Schema v1`
2. 再基于 `AgentOS接口契约与Schema定义.md` 生成一份 `OpenAPI v1` 草案
3. 再开始 `Spring Boot` 工程初始化
4. 先落地认证、权限、审批、审计基础能力
5. 最后进入 Memory、Context 和业务聚合 API 的最小闭环实现

## 14. 最终结论

本次对齐后，Dev1 的事实方向已经明确：

- 后端主工程使用 `Java`
- `AgentOS服务设计方案.md` 继续作为后端总设计文档
- 本文档作为“冻结跨团队 Schema”的执行清单

如果后续要开始联调，本文档中的以下对象必须先冻结：

- `Agent Action Schema（智能体动作结构）`
- `Approval Schema（审批结构）`
- `Audit Event Schema（审计事件结构）`
- `Agent Request Schema（智能体请求结构）`
- `Agent Response Schema（智能体响应结构）`
- `Source Reference Schema（来源引用结构）`
- `Context Bundle Schema（上下文聚合结构）`
- `Knowledge Search Response Schema（知识检索响应结构）`
- `Api Response Envelope Schema（统一响应包结构）`
- `Api Error Schema（统一错误结构）`
