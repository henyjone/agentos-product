# QA：Test / Security QA 测试计划

## 职责定位

QA 负责 AgentOS MVP 的功能测试、安全测试、权限测试、Agent 行为测试、E2E 测试和内部试点验收。

这个角色不是最后才介入点页面，而是从公共契约阶段开始盯住权限、隐私、审批、审计和 Agent 安全边界。QA 对 P0/P1 权限和隐私问题拥有阻断试点权。

## 第一步：制定测试策略

### 要做什么

- 建立功能测试计划。
- 建立权限矩阵测试表。
- 建立 Agent 行为测试集。
- 建立核心 E2E 场景。
- 定义 P0/P1/P2 缺陷标准。
- 定义试点准入标准。

### 交付什么

- Test plan。
- Permission test matrix。
- Agent eval cases。
- E2E scenario list。
- Defect severity rules。

### 如何验收

- 每个 MVP 功能都有验收标准。
- 权限和隐私测试从一开始就覆盖。
- 每个角色都有明确的允许访问和禁止访问列表。
- 所有开发都能基于测试计划理解质量门槛。

## 第二步：测试公共契约

### 要做什么

- 检查 API contract 是否完整。
- 检查 Agent Action Schema 是否满足审批和审计。
- 检查 Connector 数据是否包含来源、权限、敏感等级。
- 检查前端是否展示必要解释信息。
- 检查权限矩阵是否覆盖 HR、CEO、Manager、Employee、Admin。

### 交付什么

- Contract test checklist。
- Schema issue list。
- 权限矩阵风险清单。

### 如何验收

- 契约缺字段必须在并行开发前暴露。
- 权限、审批、审计字段不能缺。
- Agent、前端、后端、数据接入对同一字段的理解一致。
- P0 级契约问题不得进入后续开发。

## 第三步：测试第一个闭环

### 要做什么

- 测试 Agent 生成高风险 action。
- 测试审批队列收到 action。
- 测试批准、拒绝、失败状态。
- 测试审计日志完整记录。
- 测试不同角色审批可见性。
- 测试未授权用户不能访问他人审批项。

### 交付什么

- First-loop E2E report。
- Blocking bugs list。
- Approval and audit test cases。

### 如何验收

- 高风险动作不能直接执行。
- 审批状态变化必须写审计。
- 审计日志包含发起人、动作、来源、审批人、结果。
- 未授权用户看不到不属于自己的审批项。
- 拒绝和失败状态都能被正确展示和追踪。

## 第四步：测试核心产品流程

### 要做什么

- 测试管理层组织简报。
- 测试项目状态助手。
- 测试员工每日简报。
- 测试共事模式。
- 测试知识检索。
- 测试审批执行。
- 测试前端页面的加载、空状态、错误状态。

### 交付什么

- MVP flow test report。
- Regression checklist。
- Core user journey test cases。

### 如何验收

- 六条核心流程都能跑通。
- Agent 回答包含模式、来源、下一步。
- 知识检索包含出处和不确定性标记。
- 前端页面不会把私人内容展示到管理视图。
- 核心路径没有 P0/P1 功能缺陷。

## 第五步：权限、安全、隐私专项测试

### 要做什么

- 测试员工私人共事讨论不会进入管理视图。
- 测试 CEO/HR 不能默认查看个人原始记忆。
- 测试 Restricted 数据不会进入普通 Agent 上下文。
- 测试越权访问。
- 测试敏感数据泄露。
- 测试 break-glass 是否有审批和审计。
- 测试 Agent 是否会把推断伪装成事实。

### 交付什么

- Security test report。
- Privacy risk list。
- Permission bypass test results。
- Agent safety test results。

### 如何验收

- 无 P0/P1 权限和隐私缺陷。
- 所有敏感访问都能追溯。
- Restricted 数据不会出现在未授权页面或 Agent 回答中。
- Agent 无来源回答必须标记不确定。
- break-glass 访问必须有原因、范围、审批和审计。

## 第六步：试点验收

### 要做什么

- 执行完整回归测试。
- 验证部署版本。
- 验证试点数据导入。
- 整理未解决风险。
- 输出是否可试点结论。
- 准备试点问题反馈模板。

### 交付什么

- Alpha readiness report。
- Known issues。
- Go / No-Go recommendation。
- 试点反馈模板。

### 如何验收

- 核心流程稳定。
- 权限和隐私风险可控。
- QA 明确给出是否可进入内部试点。
- 所有 P0/P1 问题已关闭或明确阻断试点。
- P2/P3 问题有 owner 和处理计划。

## 与其他角色的协作接口

- 与 Dev 1：验证 API contract、权限矩阵、审批流、审计日志。
- 与 Dev 2：验证 Agent 行为、模式路由、上下文权限、安全输出。
- 与 Dev 3：验证页面路径、角色化视图、审批/审计 UI、私人/公开边界。
- 与 Dev 4：验证数据来源、敏感等级、Knowledge Index、connector 泄露风险。

## 最终完成标准

- 组织简报、项目状态、个人简报、共事模式、知识检索、审批执行六条核心流程全部通过。
- 私人讨论不会出现在管理视图。
- CEO/HR 不能默认查看个人原始记忆。
- 高风险动作必须审批。
- 审计日志完整可追溯。
- QA 给出明确内部试点结论。
