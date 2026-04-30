# Dev 1：Backend / Tech Lead / Workflow 开发计划

## 职责定位

Dev 1 负责 AgentOS MVP 的系统骨架，包括后端架构、数据库、API、权限、审批、审计和 Workflow Engine。

这个角色是技术主控，需要保证前端、Agent、数据接入和测试都围绕同一套公共契约工作。

## 第一步：定义系统公共契约

### 要做什么

- 定义核心数据模型：User、Org、Team、Project、Task、Meeting、Memory、Approval、AuditEvent、ConnectorSource。
- 定义角色模型：Admin、Executive、Manager、Employee、HR。
- 定义权限矩阵：谁能看个人数据、团队数据、管理数据、敏感数据。
- 定义 Agent Action Schema。
- 定义 Approval Schema。
- 定义 Audit Event Schema。
- 定义后端 API contract，供前端、Agent、数据接入模块使用。

### 交付什么

- 数据库 schema 草案。
- API contract 文档。
- 权限矩阵文档。
- 审批状态流转定义。
- 审计事件字段定义。

### 如何验收

- Dev 2 可以基于 Agent Action Schema 生成待审批动作。
- Dev 3 可以基于 API contract 开发前端页面。
- Dev 4 可以基于 ConnectorSource 模型提供数据。
- QA 可以基于权限矩阵写测试用例。
- 高风险动作、审批、审计、权限字段都有统一定义，不能各自发明。

## 第二步：搭建后端基础工程

### 要做什么

- 搭建后端服务项目。
- 配置数据库、迁移机制和环境变量。
- 实现用户、组织、团队、角色基础 API。
- 实现认证或模拟登录能力。
- 准备 mock seed 数据。
- 提供本地启动说明。

### 交付什么

- 可启动的后端服务。
- 基础数据库迁移。
- 用户、组织、团队、角色 API。
- 初始化数据脚本。
- 后端本地开发 README。

### 如何验收

- 本地可以启动后端服务。
- 前端可以获取当前用户和角色。
- 不同角色请求同一接口时能返回不同数据范围。
- 初始化脚本可以重复执行，不产生脏数据。

## 第三步：实现审批队列和审计日志

### 要做什么

- 实现 Approval 创建、查询、批准、拒绝、执行失败状态。
- 实现 AuditEvent 写入和查询。
- 所有 Agent action 都能写入审批队列。
- 审批状态变化自动写入审计日志。
- 定义高风险动作默认进入审批队列的后端规则。

### 交付什么

- 审批队列 API。
- 审计日志 API。
- 审批状态流转逻辑。
- Agent action 到 Approval 的转换逻辑。

### 如何验收

- Agent 发起高风险动作后不会直接执行，只会生成审批项。
- 审批通过、拒绝、执行失败都会生成审计记录。
- 审计日志能查到发起人、动作内容、来源、审批人、结果。
- 未授权用户不能看到不属于自己的审批项。

## 第四步：实现核心业务 API

### 要做什么

- 实现管理层组织简报 API。
- 实现项目状态助手 API。
- 实现员工每日简报 API。
- 实现个人记忆读取和编辑 API。
- 实现知识检索结果聚合 API。
- 所有业务 API 按角色过滤返回内容。

### 交付什么

- Dashboard API。
- Project Status API。
- Personal Brief API。
- Memory API。
- Knowledge Aggregation API。
- 角色化数据过滤逻辑。

### 如何验收

- Executive 能看到组织级聚合风险。
- Manager 能看到团队项目状态和阻塞。
- Employee 只能看到自己的个人简报和授权协作数据。
- HR 不能默认读取员工个人原始记忆。
- API 返回结果能被前端直接渲染，被 Agent 直接组装上下文。

## 第五步：强化权限和敏感数据保护

### 要做什么

- 实现 Public、Internal、Private、Restricted 数据分层。
- 阻止管理层默认读取员工个人原始记忆。
- 实现 break-glass 受控访问流程的基础模型。
- 对敏感数据访问写入独立审计日志。
- 增加错误处理、操作日志和异常响应。

### 交付什么

- 权限中间件。
- 敏感数据访问拦截。
- break-glass 审批模型。
- 越权访问审计记录。

### 如何验收

- HR/CEO 不能默认查看员工私人原始记忆。
- Restricted 数据不会进入普通 Agent 上下文。
- 越权访问返回明确错误，并写入审计日志。
- break-glass 访问必须包含原因、审批人、范围、时间限制和审计记录。

## 第六步：试点版本后端收口

### 要做什么

- 整理部署配置。
- 准备试点初始化脚本。
- 整理后端 API 文档。
- 修复 QA 提出的权限、审批、审计问题。
- 保证核心闭环稳定：Agent action -> Approval -> Audit。

### 交付什么

- 可部署后端服务。
- 试点数据初始化脚本。
- 后端 API 文档。
- 后端风险清单和已知限制。

### 如何验收

- MVP 核心闭环稳定跑通。
- 审计记录完整可追溯。
- QA 无 P0/P1 权限缺陷。
- 前端、Agent、数据接入模块都能稳定调用后端接口。

## 与其他角色的协作接口

- 与 Dev 2：提供 Agent Action Schema、审批 API、上下文权限规则。
- 与 Dev 3：提供 API contract、角色化数据、审批和审计接口。
- 与 Dev 4：提供 ConnectorSource 数据模型、知识检索聚合接口、敏感等级规则。
- 与 QA：提供权限矩阵、审计样例、测试账号和测试数据。

## 最终完成标准

- 后端支持组织简报、项目状态、个人简报、共事输出、知识检索、审批、审计的完整 MVP 闭环。
- 所有高风险动作必须审批。
- 所有 Agent 读取、生成、执行动作必须可审计。
- 个人原始记忆和 Restricted 数据受到权限保护。
