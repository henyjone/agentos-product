# Dev 2：AI / Agent Engineer 开发计划

## 职责定位

Dev 2 负责 AgentOS MVP 的智能核心，包括 Agent Orchestrator、模式路由、上下文组装、共事模式、知识回答、工具调用策略和安全输出。

这个角色决定产品是否有“共同工作的搭档感”，也要保证 Agent 不越权、不绕过审批、不把推断伪装成事实。

## 第一步：定义 Agent 工作方式

### 要做什么

- 定义 Agent 模式：Personal、CoWork、Team、Management、Knowledge、Execution、Governance。
- 定义每种模式的输入、输出和使用场景。
- 和 Dev 1 对齐 Agent Action Schema。
- 和 Dev 4 对齐知识检索返回格式。
- 设计 Agent 标准回答结构。
- 设计 prompt 模板草案。

### 交付什么

- Agent mode spec。
- Prompt 模板草案。
- Agent response schema。
- Agent action 输出格式。

### 如何验收

- Agent 每次回答都能说明当前模式、使用的数据来源、是否需要确认、下一步动作。
- Dev 1 能接收 Agent 生成的 action。
- Dev 3 能渲染 Agent 结构化输出。
- Dev 4 能给 Agent 提供带来源和权限的上下文。

## 第二步：实现 Agent Orchestrator

### 要做什么

- 根据用户身份、问题、上下文判断 Agent 模式。
- 组装用户上下文、项目上下文、组织上下文和知识检索上下文。
- 输出结构化结果，而不是只输出纯文本。
- 支持工具调用前的风险判断。
- 支持无足够上下文时主动说明不确定。

### 交付什么

- Agent Orchestrator。
- Mode router。
- Context builder。
- Structured response generator。

### 如何验收

- “今天我该做什么”进入 Personal Mode。
- “这个项目有什么风险”进入 Team Mode。
- “公司今天最大风险是什么”进入 Management Mode。
- “帮我查这个客户上次为什么投诉”进入 Knowledge Mode。
- “帮我发消息给客户”进入 Execution Mode，并要求审批。

## 第三步：实现高风险动作拦截

### 要做什么

- 识别发消息、发邮件、建任务、改项目状态、访问敏感记忆等高风险动作。
- 为高风险动作生成待审批 Agent Action。
- 不直接调用执行工具。
- 把 action 发送给 Dev 1 的审批 API。
- 在 Agent 输出中解释为什么需要审批。

### 交付什么

- Risk classifier。
- Action generator。
- Approval integration。
- Approval explanation template。

### 如何验收

- Agent 无法绕过审批直接执行高风险动作。
- 每个待审批动作都有来源、影响范围、风险等级。
- 用户能看到为什么该动作需要确认。
- 审批动作能被 Dev 3 的审批 UI 正确展示。

## 第四步：实现核心 Agent 能力

### 要做什么

- 实现管理层组织简报生成。
- 实现项目状态摘要生成。
- 实现员工每日简报生成。
- 实现会议行动项生成。
- 实现知识检索问答。
- 知识回答必须区分事实、推断和建议。

### 交付什么

- Management brief chain。
- Project status chain。
- Personal brief chain。
- Meeting action item chain。
- Knowledge answer chain。

### 如何验收

- 管理简报能列出风险、原因、影响范围、建议动作。
- 项目摘要能列出进展、阻塞、依赖、待决策事项。
- 员工简报能列出今日优先级、会议准备、待回复事项。
- 知识回答必须带出处。
- 无出处时必须标记为不确定，不能伪装成事实。

## 第五步：实现共事模式

### 要做什么

- 支持员工说“陪我想一下”进入 CoWork Mode。
- 支持问题澄清、反方观点、方案比较、利益相关方分析、沟通准备。
- 支持把私人讨论整理成公开 memo、消息草稿、任务草稿。
- 默认不把私人讨论写入团队上下文。
- 公开输出必须等待用户确认。

### 交付什么

- CoWork prompt。
- Deliberation flow。
- Private-to-public output generator。
- Public output action schema。

### 如何验收

- 私人讨论和公开输出明确分离。
- Agent 能帮助用户把模糊想法整理成可发出的版本。
- 公开输出必须经用户确认。
- Agent 不会自动把员工真实顾虑推送给管理层或团队。

## 第六步：Agent 质量和安全收口

### 要做什么

- 增加敏感数据过滤。
- 增加无来源回答保护。
- 建立 Agent 行为测试集。
- 根据 QA 反馈修正错误路由、越权上下文和不稳定输出。
- 优化核心场景输出质量。

### 交付什么

- Safety rules。
- Agent eval cases。
- 输出质量优化版本。
- Agent 已知限制说明。

### 如何验收

- Agent 不把推断伪装成事实。
- Agent 不输出未授权私人记忆。
- Agent 不绕过审批。
- 核心场景回答稳定、可解释、可追溯。
- QA 的 Agent 行为测试集通过。

## 与其他角色的协作接口

- 与 Dev 1：使用 Agent Action Schema、审批 API、权限规则。
- 与 Dev 3：提供结构化 Agent 输出、模式标记、来源引用、审批提示。
- 与 Dev 4：使用 Knowledge Index、Context Retrieval API、来源和敏感等级。
- 与 QA：提供 Agent eval cases、风险场景、预期输出。

## 最终完成标准

- Agent 能在 Personal、CoWork、Team、Management、Knowledge、Execution 模式间正确路由。
- Agent 回答可解释、带来源、能区分事实和推断。
- 高风险动作只生成审批项，不直接执行。
- 共事模式具备真实搭档感，并保护私人讨论边界。
