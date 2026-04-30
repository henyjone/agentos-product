# HGZ Dev2 AI 智能体模块独立设计方案

版本：v0.1  
日期：2026-04-30  
负责人：HGZ  
对应角色：Dev 2 - AI / Agent Engineer

---

## 1. 文档目标

本文档用于定义 HGZ 在 AgentOS MVP 中负责的 AI 智能体模块。

本方案从原 DailySync 端到端设计中抽离出“Dev2 可独立负责”的部分，重点解决：

- Agent 如何识别用户意图并进入正确模式
- Agent 如何组装上下文并生成结构化回答
- Agent 如何区分事实、推断和建议
- Agent 如何识别高风险动作并生成待审批 action
- Agent 如何支持管理简报、项目状态、个人简报、知识问答和共事模式
- Agent 记忆能力如何通过统一接口接入，而不是直接依赖文本文件或数据库实现

本文档不替代 Dev1 / Dev3 / Dev4 的设计。

---

## 2. 职责定位

HGZ 负责 AgentOS MVP 的智能核心，模块名称建议为：

```text
agent_engine
```

该模块是 Python 智能体层，位于后端 API、数据接入、知识检索和前端工作台之间。

核心职责：

- Agent 模式定义与路由
- 上下文组装策略
- Prompt / chain 设计
- 结构化响应生成
- 高风险动作识别
- Agent Action 生成
- 安全输出检查
- Agent 行为测试集
- 记忆接口抽象与使用策略

一句话定位：

> agent_engine 不负责存储、同步和展示，只负责把受控上下文转化为可信、可解释、可审批的智能体输出。

---

## 3. 与团队角色的边界

### 3.1 HGZ 负责实现

| 范围 | 说明 |
|---|---|
| Agent mode spec | Personal / CoWork / Team / Management / Knowledge / Execution / Governance |
| Mode router | 根据用户身份、问题和上下文判断模式 |
| Context builder | 调用 Dev4 / Dev1 提供的上下文接口，组装给模型的输入 |
| Prompt templates | 各模式 prompt、报告 prompt、知识问答 prompt、共事 prompt |
| Chain runner | 管理简报、项目摘要、个人简报、会议行动项、知识问答 |
| Structured response | 输出统一 JSON，供前端渲染 |
| Risk classifier | 识别发消息、发邮件、建任务、改状态、敏感访问等高风险动作 |
| Action generator | 为高风险动作生成待审批 Agent Action |
| Safety guard | 检查无来源回答、越权内容、事实/推断混淆、敏感信息 |
| Agent eval cases | 提供 QA 可运行的行为测试集 |
| Memory client | 定义 Agent 使用记忆的接口，不直接绑定存储实现 |

### 3.2 HGZ 不负责主实现

| 范围 | 主要负责人 | HGZ 的参与方式 |
|---|---|---|
| 数据库 schema | Dev1 | 提需求字段和使用方式 |
| 后端 API | Dev1 | 对齐 contract，调用 API |
| 审批队列状态机 | Dev1 | 生成 Agent Action，不直接落库 |
| 审计日志 | Dev1 | 提供审计事件内容建议 |
| Web 工作台 | Dev3 | 提供 Agent response schema |
| 卡片 UI / 页面展示 | Dev3 | 提供结构化数据和来源引用 |
| Gitea / Jira / Notion 接入 | Dev4 | 使用只读上下文和 Knowledge Index |
| Knowledge Index | Dev4 | 定义检索结果对 Agent 的最低字段要求 |
| 原始数据同步任务 | Dev4 / Dev1 | 只消费同步后的上下文 |

---

## 4. 总体架构

```text
用户问题 / 定时任务 / 页面触发
        |
        v
+----------------------------+
|        agent_engine        |
|----------------------------|
| Mode Router                |
| Context Builder            |
| Prompt Manager             |
| Chain Runner               |
| Structured Response Builder|
| Risk Classifier            |
| Action Generator           |
| Safety Guard               |
+----------------------------+
        |
        +---- Dev1 Backend API
        |     - user / role / permission
        |     - approval API
        |     - audit API
        |
        +---- Dev4 Context / Knowledge API
        |     - context retrieval
        |     - knowledge search
        |     - source reference
        |     - sensitivity level
        |
        +---- Dev3 Web UI
              - render response
              - show sources
              - show approval hints
```

关键原则：

- Agent 不直接读取数据库。
- Agent 不直接同步外部工具。
- Agent 不直接执行高风险动作。
- Agent 不直接决定用户能看什么，权限判断由 Dev1 / Dev4 的接口先完成。
- Agent 输出必须结构化、可解释、可追溯。

---

## 5. Agent 模式设计

| 模式 | 触发示例 | 主要输出 |
|---|---|---|
| Personal | 今天我该做什么？ | 今日优先级、会议准备、待回复事项 |
| CoWork | 陪我想一下这个方案 | 澄清问题、反方观点、方案比较、公开输出草稿 |
| Team | 这个项目有什么风险？ | 进展、阻塞、依赖、待决策事项 |
| Management | 公司今天最大风险是什么？ | 组织风险、影响范围、建议动作 |
| Knowledge | 这个客户上次为什么投诉？ | 带出处的事实、推断、建议 |
| Execution | 帮我发消息给客户 | 待审批 action、风险说明 |
| Governance | 谁访问过敏感记忆？ | 审计查询建议、权限边界说明 |

模式路由不只看关键词，还需要结合：

- 当前用户角色
- 当前页面或入口
- 上下文权限
- 是否包含执行动作
- 是否请求敏感信息
- 是否需要知识检索

---

## 6. 标准响应结构

Agent 对前端和后端输出统一结构。

```json
{
  "mode": "management",
  "answer": {
    "summary": "今天最大的风险是支付项目验收延期。",
    "facts": [],
    "inferences": [],
    "suggestions": []
  },
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

要求：

- `facts` 必须来自 source。
- `inferences` 必须标明推断依据。
- `suggestions` 不得伪装成事实。
- 无 source 的知识回答必须标记不确定。
- 涉及高风险动作时，`requires_confirmation` 必须为 true。

---

## 7. 高风险动作和审批

Agent 可以建议动作，但不能绕过审批直接执行。

第一版高风险动作包括：

- 发消息
- 发邮件
- 创建正式任务
- 修改项目状态
- 对外沟通
- 访问 Private / Restricted 记忆
- 生成可能影响管理判断的正式报告
- 更新客户记录
- 任何影响绩效、人事、财务、法务的数据处理

高风险动作输出为 Agent Action：

```json
{
  "action_type": "send_message",
  "title": "发送客户跟进消息",
  "target": {
    "system": "feishu",
    "recipient": "customer_success_group"
  },
  "payload": {},
  "risk_level": "high",
  "reason": "该动作会向外部或跨团队对象发送正式消息。",
  "sources": [],
  "requires_approval": true
}
```

该 action 由 Dev1 审批 API 接收，Dev3 负责展示和确认。

---

## 8. 记忆系统设计

### 8.1 结论

记忆系统不建议让 Agent 直接读写文本文件，也不建议第一版就把 Agent 和某个数据库强绑定。

推荐设计：

```text
Agent
  -> MemoryClient interface
      -> FileMemoryAdapter       MVP / 本地开发
      -> BackendMemoryAdapter    正式集成 Dev1 API
      -> DatabaseMemoryAdapter   可选，直接接 PostgreSQL / SQLite
```

### 8.2 文本文件可以保留的内容

以下内容可以继续用 Markdown / YAML / JSON 文件管理：

- prompt 模板
- 系统规则草案
- eval cases
- 本地开发 mock memory
- 人工整理的示例上下文

### 8.3 不建议只放文本文件的内容

以下内容正式环境应通过 Dev1 后端或数据库保存：

- 管理者偏好
- 员工项目关系
- 项目长期背景
- 团队上下文
- 重要决策记录
- 审计记录
- 需要权限控制的个人记忆

### 8.4 MemoryClient 最低字段

记忆读写接口至少保留：

```text
id
owner_id
scope
section
content
source
source_id
sensitivity
created_at
updated_at
version
```

Agent 只依赖这些字段，不关心底层是文件、数据库还是后端 API。

---

## 9. 核心 Chain

### 9.1 Management Brief Chain

输入：

- 组织级风险上下文
- 项目状态上下文
- 客户事件上下文
- 近期会议 / 决策上下文
- 管理者偏好

输出：

- 今日组织状态
- 最大风险
- 影响范围
- 原因
- 建议动作
- 需要确认的动作

### 9.2 Project Status Chain

输入：

- 项目上下文
- 任务 / PR / issue / 会议摘要
- 阻塞和依赖信息

输出：

- 当前进展
- 阻塞
- 依赖
- 待决策事项
- 下一步建议

### 9.3 Personal Brief Chain

输入：

- 当前用户任务
- 日程
- 会议准备
- 待回复事项
- 授权个人记忆

输出：

- 今日优先级
- 会议准备
- 等待用户处理事项
- 用户阻塞他人的事项

### 9.4 Knowledge Answer Chain

输入：

- Knowledge Index 检索结果
- source reference
- sensitivity level

输出：

- 事实
- 推断
- 建议
- 出处
- 不确定性说明

### 9.5 CoWork Chain

输入：

- 用户私人讨论上下文
- 用户明确授权的相关背景

输出：

- 问题澄清
- 反方观点
- 方案比较
- 沟通准备
- 可公开 memo / 消息 / 任务草稿

默认规则：

- 私人讨论不自动进入团队上下文。
- 公开输出必须由用户确认。
- 不把员工真实顾虑自动推送给管理层。

---

## 10. Python 模块结构

第一版代码目录建议：

```text
src/
  agent_engine/
    __init__.py
    modes.py
    schemas.py
    router.py
    risk.py
    orchestrator.py
    memory.py
    README.md

tests/
  agent_engine_tests/
    test_router.py
    test_risk.py
```

其中：

- `modes.py` 定义 AgentMode。
- `schemas.py` 定义结构化输入输出。
- `router.py` 实现基础模式路由。
- `risk.py` 实现高风险动作识别。
- `orchestrator.py` 串联路由、上下文、响应和风险判断。
- `memory.py` 定义 MemoryClient 协议和 file-backed adapter 占位。

---

## 11. 与其他同事的接口清单

### 11.1 依赖 Dev1

- 当前用户和角色
- 权限判断结果
- Agent Action Schema
- Approval API
- Audit API
- Memory API 或记忆存储 API

### 11.2 依赖 Dev3

- Agent response schema 渲染方式
- source reference 展示组件
- approval hint 展示组件
- fact / inference / suggestion 展示组件

### 11.3 依赖 Dev4

- Context Retrieval API
- Knowledge Search API
- source reference format
- sensitivity level
- mock context dataset

---

## 12. 验收标准

第一阶段完成标准：

- Agent 能识别 Personal / CoWork / Team / Management / Knowledge / Execution 模式。
- Agent 输出统一结构化 JSON。
- 知识回答能区分事实、推断和建议。
- 无出处时能明确标记不确定。
- 高风险动作只生成审批 action，不直接执行。
- 私人共事内容不会自动进入团队或管理上下文。
- MemoryClient 支持 file adapter 开发态使用，并可替换为 Dev1 后端 API。
- QA 可以基于 eval cases 验证路由、越权、审批和无来源回答场景。

---

## 13. 第一阶段开发顺序

1. 建立 `agent_engine` Python 包和测试目录。
2. 实现 `AgentMode`、`AgentRequest`、`AgentResponse`、`AgentAction` 等基础 schema。
3. 实现基础 Mode Router。
4. 实现基础 Risk Classifier。
5. 实现 Orchestrator 最小闭环。
6. 增加 MemoryClient 协议，不绑定具体存储。
7. 和 Dev1 对齐 Agent Action Schema。
8. 和 Dev3 对齐 Agent Response Schema。
9. 和 Dev4 对齐 Context Retrieval / Knowledge Search 返回格式。
10. 编写 Agent eval cases，覆盖核心路由和安全边界。
