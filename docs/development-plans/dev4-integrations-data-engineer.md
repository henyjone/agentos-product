# Dev 4：Integrations / Data / Knowledge Engineer 开发计划

## 职责定位

Dev 4 负责 AgentOS MVP 的数据和集成底座，包括 mock connector、真实工具只读接入、Knowledge Index、数据来源、权限范围、敏感等级和同步任务。

这个角色要保证 Agent 和前端拿到的数据可追溯、可过滤、可审计，不让敏感数据进入错误上下文。

## 第一步：定义数据接入标准

### 要做什么

- 定义 Connector Interface。
- 定义数据来源字段：source、source_url、timestamp、owner。
- 定义权限字段：permission_scope。
- 定义敏感等级：Public、Internal、Private、Restricted。
- 定义数据内容结构：content、metadata、entity_type、entity_id。
- 准备 mock 数据结构。

### 交付什么

- Connector spec。
- Sensitivity spec。
- Mock data schema。
- Source reference format。

### 如何验收

- 所有外部数据进入系统时都有来源、权限、敏感等级。
- Dev 2 可以基于 source reference 做带出处回答。
- Dev 3 可以展示数据来源和敏感等级。
- QA 可以基于敏感等级做泄露测试。

## 第二步：实现 mock connector

### 要做什么

- 实现项目管理 mock connector。
- 实现文档/知识库 mock connector。
- 实现聊天/会议 mock connector。
- 实现客户事件 mock connector。
- 为管理简报、项目状态、个人简报准备 demo 数据。
- 为共事模式准备私人讨论和公开输出样例数据。

### 交付什么

- Mock connector package。
- Demo dataset。
- Mock data README。

### 如何验收

- 不接真实工具也能跑通 MVP。
- Agent 和前端可以使用同一套 mock 数据。
- mock 数据覆盖管理层、团队负责人、员工三类角色。
- mock 数据包含正常数据、敏感数据、越权场景数据。

## 第三步：实现 Knowledge Index 基础版

### 要做什么

- 索引文档、会议、任务、项目、客户事件。
- 支持关键词检索。
- 支持按项目、客户、会议、人员过滤。
- 检索结果返回出处、时间、权限、敏感等级。
- 对 Restricted 数据执行默认过滤。

### 交付什么

- Knowledge Index。
- Search API 或 search adapter。
- Source reference format。
- 基础检索测试数据。

### 如何验收

- 知识检索结果都能回溯来源。
- Restricted 数据不会返回给未授权用户。
- 检索结果能被 Dev 2 用于知识回答。
- 检索结果能被 Dev 3 展示为出处列表。

## 第四步：支持 Agent 上下文检索

### 要做什么

- 为 Dev 2 提供 context retrieval API。
- 支持按 Agent 模式返回不同上下文。
- Personal Mode 只返回个人授权上下文。
- CoWork Mode 默认使用私人上下文。
- Team Mode 返回团队项目上下文。
- Management Mode 返回聚合和业务例外上下文，不返回私人讨论。
- Knowledge Mode 返回带出处的检索结果。

### 交付什么

- Context retrieval service。
- Mode-aware retrieval rules。
- 权限过滤测试样例。

### 如何验收

- Agent 不会拿到超出当前用户权限的数据。
- 管理简报不会包含员工私人讨论内容。
- 共事模式的私人上下文不会自动进入团队上下文。
- 检索返回结果都有权限和敏感等级。

## 第五步：接入真实只读工具

### 要做什么

- 选择 1-2 个真实工具只读接入，优先 GitHub、Notion、Linear/Jira。
- 实现 OAuth/token 配置或本地配置。
- 实现基础同步任务。
- 实现增量同步基础能力。
- 同步数据必须打来源、权限和敏感等级标签。

### 交付什么

- 至少 1 个真实 connector。
- 同步任务。
- Connector 配置说明。
- 只读接入限制说明。

### 如何验收

- 真实工具数据可进入 Knowledge Index。
- 真实数据不会绕过权限和敏感等级规则。
- 同步失败有错误日志。
- 系统能在真实 connector 不可用时回退到 mock 数据。

## 第六步：数据质量和试点准备

### 要做什么

- 做数据去重。
- 做来源合并。
- 准备试点数据导入脚本。
- 和 QA 一起做敏感数据泄露测试。
- 整理数据质量报告。

### 交付什么

- Data import script。
- Data quality report。
- Connector README。
- 敏感数据测试样例。

### 如何验收

- 试点数据可重复导入。
- 知识检索结果稳定。
- 敏感数据不会进入错误视图或错误 Agent 上下文。
- QA 的敏感数据泄露测试通过。

## 与其他角色的协作接口

- 与 Dev 1：使用 ConnectorSource 模型、权限规则、知识聚合接口。
- 与 Dev 2：提供 Knowledge Index、Context Retrieval API、来源引用和敏感等级。
- 与 Dev 3：提供检索结果结构、source reference、敏感等级展示字段。
- 与 QA：提供敏感数据样例、越权数据样例、同步失败样例。

## 最终完成标准

- MVP 可以基于 mock connector 跑通完整演示。
- 至少一个真实工具完成只读接入。
- 所有数据都有来源、权限范围和敏感等级。
- Knowledge Index 支持核心检索场景，并且不泄露 Restricted 数据。
