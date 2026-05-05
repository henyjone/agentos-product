# AgentOS 服务设计方案（Dev1 Java 版）

## 1. 文档定位

本文档只描述 AgentOS Dev1 后端的方案设计，不再承载字段级表定义、接口路径、共享 Schema 样例等契约细节。

详细契约文档请查看：

- `docs/ZJQ个人文档/AgentOS数据库模型定义.md`
- `docs/ZJQ个人文档/AgentOS接口契约与Schema定义.md`
- `docs/ZJQ个人文档/Dev1-跨团队Schema冻结方案.md`

本文档回答三个问题：

1. Dev1 后端为什么这样设计
2. Java 后端在 AgentOS 中承担什么职责
3. 各模块如何形成 MVP 闭环

## 2. 设计目标

AgentOS 后端要支撑 MVP 的核心闭环：

```text
用户 / 前端 -> Agent -> 后端上下文与权限 -> Agent Action -> Approval -> Execution -> Audit -> 可追溯结果
```

同时满足以下业务约束：

- 管理层可以看组织级聚合信息，但不能默认读取员工私人原始数据
- 员工可以使用个人模式和共事模式，但私人内容不得自动升级为团队或组织内容
- 高风险动作必须先审批，不能由 Agent 直接执行
- 所有关键读取、生成、审批、执行动作都必须可审计
- 所有接入数据都必须带来源、权限范围和敏感等级

## 3. 核心设计原则

### 3.1 `Contract First（契约优先）`

先冻结共享 Schema、API 契约和权限规则，再落数据库、DTO 和实现代码。

### 3.2 `Default Deny（默认拒绝）`

对 `private` 和 `restricted` 数据默认拒绝访问，除非存在显式授权、审批或 break-glass 流程。

### 3.3 `Approval Before Action（审批先于执行）`

高风险动作先转为审批对象，由人确认后再执行，避免 Agent 直接修改正式系统状态。

### 3.4 `Audit By Default（默认审计）`

关键读写、越权尝试、审批变更、执行结果、外部调用都要记录审计事件。

### 3.5 `Agent Is Not Trusted（Agent 默认不可信）`

Agent 可以提出建议、生成动作、消费上下文，但不能绕过权限、审批和审计。

## 4. 技术选型

Dev1 后端正式采用 Java 技术路线：

- Web 框架：`Spring Boot 3.x`
- 安全框架：`Spring Security`
- 数据访问： `MyBatis`
- 数据库：`PostgreSQL 16+`
- 缓存 / 队列：`Redis`
- 异步任务：`Spring Scheduler` + `Spring Async`
- 数据迁移：`Flyway`
- API 契约：`OpenAPI 3.x`
- 认证：`JWT + Refresh Token`
- 对象存储(暂不考虑)：`MinIO` 或 `S3`
- 检索：`PostgreSQL GIN + pgvector`

选用 Java 的原因：

- Dev1 负责的是长期演进的主后端，而不是一次性 AI demo
- 权限、审批、审计、Workflow 都属于强约束、强治理场景
- Java 在分层设计、类型约束、多人协作、长期维护上更稳定
- Dev2 的 `Python` Agent 模块可以独立保留，通过 HTTP/OpenAPI 对接，不需要强行统一语言

## 5. 系统职责边界

### 5.1 Dev1 后端负责

- 身份、组织、团队、角色和权限边界
- 项目、任务、会议、记忆等核心业务实体管理
- Agent 上下文聚合入口
- 高风险动作的审批流和执行编排
- 审计日志与可追溯能力
- 对外 API 契约与跨团队公共模型

### 5.2 Dev1 后端不负责

- LLM 推理本身
- Prompt 设计和链路编排细节
- 复杂知识抽取与智能总结算法
- 前端渲染实现
- 外部数据源的全部采集逻辑细节

这些分别由 Dev2、Dev3、Dev4 负责，但都依赖 Dev1 冻结后的契约工作。

## 6. 逻辑架构

```text
Client / Frontend
  -> API Gateway / Spring MVC Controllers
      -> Auth / RBAC / ABAC
      -> Domain Application Services
          -> Identity Service
          -> Project Service
          -> Memory Service
          -> Context Service
          -> Approval Service
          -> Audit Service
          -> Connector Service
      -> Persistence Layer
          -> PostgreSQL
          -> Redis
          -> Object Storage
```

### 6.1 分层说明

- `Controller` 层：接收 HTTP 请求，做输入校验和响应包装
- `Application Service` 层：编排领域逻辑和跨模块流程
- `Domain` 层：承载审批、审计、权限、状态流转等核心业务规则
- `Persistence` 层：负责实体持久化、查询、缓存和检索支持

### 6.2 架构重点

- 对外统一暴露 `/api/v1` 契约
- 权限过滤不能下沉到前端或 Agent 侧假设，必须在服务端落地
- 上下文获取与高风险执行必须拆成不同流程
- 审计日志采用只追加模型，禁止覆盖历史

## 7. 领域划分

系统划分为五个主要领域：

- `Identity`：组织、团队、用户、角色、权限
- `Work Management`：项目、任务、会议、行动项
- `Memory & Knowledge`：记忆、来源引用、知识检索聚合
- `Workflow Governance`：Agent Action、审批、审计、break-glass
- `Connector Ingestion`：外部来源接入、同步、来源映射

这样的划分可以保证：

- 业务实体与治理实体解耦
- Dev2 可以专注消费上下文和提交动作
- Dev3 可以稳定依赖角色化 API
- Dev4 可以围绕来源、权限、敏感等级提供数据

## 8. 核心业务闭环

### 8.1 上下文读取闭环

```text
用户请求 -> Dev2 判断模式 -> Dev1 / Dev4 提供权限过滤后的上下文 -> Dev2 生成结构化回答
```

关键要求：

- 返回前必须完成角色过滤
- `restricted` 内容默认不能进入普通上下文
- 返回结果必须带来源信息，支持前端展示和 Agent 追溯

### 8.2 动作审批闭环

```text
Agent 生成动作 -> Dev1 风险判定 -> 需要审批则创建 Approval -> 审批通过后执行 -> 写入 AuditEvent
```

关键要求：

- 高风险动作不能直写正式系统
- 审批状态变化必须触发新增审计事件
- 执行失败必须保留失败记录和补偿信息

### 8.3 Break-Glass 闭环

```text
访问 restricted 数据 -> 提交受控访问申请 -> 审批 -> 临时授予 -> 超时回收 -> 审计留痕
```

关键要求：

- 必须有访问原因、范围、审批人、时效
- 不允许静默访问敏感原文
- 必须支持 QA 对越权路径做验证

## 9. 权限与信任设计

### 9.1 角色设计

MVP 固定五类角色：

- `Admin`
- `Executive`
- `Manager`
- `Employee`
- `HR`

角色设计原则：

- `Admin` 不等于业务超级用户
- `Executive` 以聚合信息为主，不以员工私人细节为主
- `Manager` 以团队边界为主
- `Employee` 以本人上下文和授权协作为主
- `HR` 可看合规所需结构化信息，但不能默认看私人原始记忆

### 9.2 数据分层

数据按敏感等级分层：

- `public`
- `internal`
- `private`
- `restricted`

其中：

- `private` 默认仅本人和授权协作者可见
- `restricted` 默认不进入普通 Agent 上下文和普通检索结果

### 9.3 信任边界

AgentOS 必须从后端明确表达两条边界：

- 员工的私人讨论默认不自动进入管理视图
- 管理层获取的是组织信号和聚合风险，不是员工监控视图

## 10. 与其他角色的协作边界

### 10.1 与 Dev2

- Dev1 提供 `Context API`、`Agent Action API`、审批规则、权限规则
- Dev2 提供结构化请求、结构化响应、动作生成逻辑

### 10.2 与 Dev3

- Dev1 提供角色化数据、审批接口、审计接口、记忆接口
- Dev3 负责把模式、来源、审批要求和权限边界清晰呈现

### 10.3 与 Dev4

- Dev1 提供 `ConnectorSource` 模型、上下文契约、敏感等级规则
- Dev4 负责来源接入、检索、来源引用和权限元数据

### 10.4 与 QA

- Dev1 提供权限矩阵、错误码、测试账号、审计样例
- QA 基于冻结契约验证越权、审批、审计、敏感数据泄露

## 11. 开发实施路线

### 11.1 第一阶段：冻结契约

先冻结：

- 共享 Schema
- API 契约
- 数据模型
- 权限矩阵
- 审批状态流转
- 审计事件规则

### 11.2 第二阶段：基础工程搭建

建立：

- `Spring Boot` 工程骨架
- 认证与权限中间层
- 数据迁移机制
- 基础种子数据
- 组织、用户、团队、项目、任务基础能力

### 11.3 第三阶段：审批与审计闭环

落地：

- `Agent Action -> Approval -> Audit Event`
- 风险判定规则
- 审批状态机
- 执行失败处理

### 11.4 第四阶段：业务 API 收口

落地：

- 管理简报
- 项目状态助手
- 个人简报
- Memory
- Knowledge / Context

### 11.5 第五阶段：联调与安全验证

完成：

- 与 Dev2 的动作和上下文联调
- 与 Dev3 的审批、审计、记忆页面联调
- 与 Dev4 的来源和检索联调
- 与 QA 的越权、权限和审计验证

## 12. 文档拆分说明

为了避免设计文档过载，本次拆分后各文档职责如下：

- `AgentOS服务设计方案.md`
  - 只描述目标、原则、架构、边界、闭环和实施路线
- `AgentOS数据库模型定义.md`
  - 维护核心实体、表结构、关联表、索引建议、落库约束
- `AgentOS接口契约与Schema定义.md`
  - 维护 API 定义、共享 Schema、错误结构、分页结构、认证结构
- `Dev1-跨团队Schema冻结方案.md`
  - 维护冻结范围、缺口清单、版本治理和验收标准

## 13. 结论

Dev1 后端的定位已经明确：

- 主后端采用 `Java`
- 设计文档只负责表达“为什么这样设计”和“整体如何运转”
- 细节契约下沉到专门的模型文档和接口文档

后续所有实现都应围绕同一目标展开：

- 高风险动作必须审批
- 审批与执行必须审计
- 角色权限必须一致
- 私人和 `restricted` 数据必须受控
- 前端、Agent、Connector、QA 基于同一套冻结契约工作
