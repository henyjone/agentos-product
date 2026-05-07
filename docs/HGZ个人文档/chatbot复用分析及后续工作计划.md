# chatbot 工程复用分析 & agent_engine 后续工作计划

> 撰写：HGZ
> 日期：2026-05-06
> 范围：D:\pro\chatbot → D:\pro\agentos-product 的跨项目复用分析，以及 agent_engine 近中期实施路线

---

## 一、核心判断：两个项目不应完全架构对齐

### 1.1 根本定位不同

| 维度 | chatbot | agentos-product | 架构含义 |
|------|---------|-----------------|----------|
| 层次 | **Agent 内核层** | **AI OS 应用层** | 内核管资源/进程/I/O，应用管组织/角色/审批 |
| 用户 | 单用户 | 多用户 + 角色 | 权限体系根本不同 |
| 执行模式 | 通用 ReAct 循环 | 手写场景 chain | chain 是 built-in 的，不是 plugin |
| Skill | YAML 插件（可扩展） | 7 种内置 mode | 不需要动态发现和装配 |
| 记忆 | 3 层个人记忆 | 组织级实体/事实/关系 | 数据模型完全不同 |
| 存储 | 本地文件 | 规划 DB 持久化 | 读写路径不同 |
| 调用方 | CLI/HTTP/WS 自建入口 | Java 后端 API 调用 | 不需要自带传输层 |

**结论**：chatbot 做的是"操作系统内核"，agentos-product 做的是"企业应用"。强行让两者模块化对齐 = 让内核和应用共享架构 → 两边都会被拖慢。

### 1.2 共享边界

```
             ┌──────────────────────────┐
             │  通用工具层（可以共享）      │
             │  EventBus, ModelClient,   │
             │  TokenCounter, Sanitize,  │
             │  ToolResult 数据结构       │
             └──────────┬───────────────┘
                        │
        ┌───────────────┼───────────────┐
        ▼                               ▼
┌───────────────┐               ┌───────────────┐
│   chatbot     │               │  agentos      │
│   Agent 内核   │               │  AI OS 应用    │
├───────────────┤               ├───────────────┤
│ RuntimeCore   │               │ agent_engine  │
│ TurnEngine    │               │   chains      │
│ Skill 系统    │               │ org_memory    │
│ 3层个人记忆   │               │ commit_guide  │
│ PolicyGuard   │               │ repo_analyzer │
│ 传输层        │               │               │
└───────────────┘               └───────────────┘
    各自独立                        各自独立
```

**共享层以少量通用工具和协议结构为主。EventBus、Sanitize、TokenCounter 可以近似直接复用；ModelProvider/adapters 需要裁剪和适配现有 config.json，不应按整套运行时搬迁。其他模块各自独立演进。**

### 1.3 明确不共享的组件及原因

| 组件 | 不共享原因 |
|------|-----------|
| RuntimeCore / TurnEngine | agent_engine 的 chain 是场景化手写流程，不是通用 ReAct 循环。强行引入会多一层抽象，MVP 阶段浪费 |
| Skill 插件系统 | agent_engine 的 7 种 mode 是内置的，不需要 YAML 发现、动态导入、注册表。未来如果有"第三方 chain 市场"才需要 |
| 3 层个人记忆 | org_memory 的数据模型（Entity/Event/Fact/Relationship）和组织权限体系跟 chatbot 的个人 JSONL 存储完全不同 |
| 传输层 | agentos-product 由 Java 后端 API 调用，不需要 Python 侧自建 HTTP/WS/CLI |
| PolicyGuard | 不直接共享 chatbot 的单用户策略实现；可参考其结构化决策对象，最终仍需和 org_memory 的 AccessContext + 审批队列对齐 |
| Session 管理 | chatbot 是单用户对话流，agentos 是多用户 + 角色切换 + 审计上下文 |

---

## 二、组件逐项判断

| 编号 | chatbot 组件 | 判断 | 理由 |
|------|-------------|------|------|
| S1 | **EventBus** | ✅ 直接复制 | 零依赖纯工具，进程内 pub/sub，通配符匹配。俩项目都用得到 |
| S2 | **ModelProvider** + adapters | ✅ 裁剪复用 | ABC 接口可以复用；adapters.py 包含 stream、async、Ollama、tool call 等较重逻辑，需要按 agentos-product 的 config.json 和 MVP 模型调用方式裁剪 |
| S3 | **TokenCounter** | ✅ 直接复制 | tiktoken 计数 + 降级策略。纯工具函数 |
| S4 | **Sanitize** | ✅ 直接复制 | 日志脱敏、API key 过滤。纯工具函数 |
| S5 | **ToolResult 数据结构** | ✅ 直接复制 | `success/content/data/error/metadata` 结构通用，不依赖任何上下文 |
| R1 | **RuntimeCore + TurnEngine** | ❌ 不共享 | 通用 ReAct 循环 vs agent_engine 的场景 chain，执行模型根本不同 |
| R2 | **Skill 插件系统** | ❌ 不共享 | YAML 发现 + 动态导入 + 注册表 → agent_engine 的 7 种 mode 是 built-in 的，不需要插件架构 |
| R3 | **SkillExecutor** | ❌ 不共享 | 依赖 Skill 注册表的编排器，agent_engine 的 orchestrator 是模式路由 + chain 调度，不是 skill 执行 |
| R4 | **3 层个人记忆** | ❌ 不共享 | JSONL session + Markdown midterm + MEMORY.md longterm vs org_memory 的 Entity/Event/Fact/Relationship 模型 |
| R5 | **PolicyGuard** | ❌ 不直接共享 | chatbot 的单用户策略 vs agentos 的多角色 AccessContext + 审批队列；但可参考 PolicyDecision / PermissionDecision 的结构化返回方式 |
| R6 | **传输层** (chat_module) | ❌ 不共享 | agentos-product 由 Java 后端 API 调用，不需要 Python 侧 HTTP/WS |
| R7 | **Session 管理** | ❌ 不共享 | 单用户对话流 vs 多用户 + 角色切换 + 审计上下文 |

**最终共享少量工具和协议结构，业务运行时、记忆模型、权限模型各自独立。**

---

## 三、共享组件详细说明

### 3.1 EventBus（S1 — 直接复制）

零依赖纯工具。进程内 pub/sub，支持通配符订阅（`*`, `prefix.*`）、sync+async handler。

```python
from common.event_bus import EventBus
bus = EventBus()
bus.subscribe("agent.*", lambda ev: print(ev.payload))
bus.emit("agent.routed", mode="management")
```

放到 `src/common/event_bus.py`，两个项目都 import 同一份代码。

### 3.2 ModelClient + adapters（S2 — 裁剪复用）

chatbot 的 `ModelProvider` ABC 可以直接作为接口参考。`OpenAIChatModelSlot` / `OllamaChatModelSlot` 适配器具备复用价值，但不建议整文件搬迁，因为当前 `chat_module/adapters.py` 同时包含 stream、async、Ollama native、tool call、embedding 等多类能力。

MVP 阶段建议只裁剪出 agentos-product 当前需要的部分：

- OpenAI-compatible chat completions 调用
- 与现有 `config.json` 兼容的 base_url / api_key / model 读取
- timeout、temperature、max_output_tokens
- 返回 `content` 和可选 `tool_calls`

复制后 agent_engine 的 ModelClient：
```python
class ModelClient(ABC):
    def generate(self, *, messages, temperature, max_output_tokens, timeout, tools=None) -> dict:
        """返回 {"content": str, "tool_calls": [...]}"""
```

配合现有 `config.json` 的模型配置工作。后续如果需要本地模型或流式输出，再补 Ollama / stream 分支。

### 3.3 TokenCounter / Sanitize / ToolResult（S3-S5 — 直接复制）

纯函数工具，不改逻辑，改 import 路径即可。

### 3.4 记忆系统 —— 不共享，但 complement

两套记忆是互补关系，不是替换关系：

| | org_memory | chatbot 3 层记忆 |
|--|------------|-------------------|
| 定位 | 组织级 | 个人级 |
| 数据 | Entity/Event/Fact/Relationship | JSONL session / Daily MD / MEMORY.md |
| 可见性 | 按角色/权限 | 仅本人 |
| 场景 | 管理者日报、项目状态 | 单用户对话延续 |

agent_engine 的 chain 需要同时访问两类记忆：调用 `org_memory` 获取组织上下文，未来通过个人记忆层获取用户对话历史。但这两层的实现和数据模型**独立演进**。

### 3.5 chain 执行模型 —— 不共享

agent_engine 的 chain 是简化的场景化流程，不是通用 ReAct 循环：

```
AgentChain.run(request):
  1. 构造 prompt（system + 上下文）
  2. ModelClient.generate()
  3. 解析 → 填充 AgentResponse
```

不需要 RuntimeCore 的任务生命周期（PENDING→RUNNING→COMPLETED/FAILED）、不需要 TurnEngine 的 tool loop（最多 10 轮的 ReAct）。chain 就是一段手写的业务逻辑，这跟 chatbot 的通用执行引擎是两回事。

---

## 四、当前阶段路线图

基于当前代码状态，建议先把已经存在的 `repo_analyzer`、`org_memory`、`commit_guide` 串成闭环，再逐步补强 `agent_engine`。这样能最快形成可演示价值，也避免先搭一套漂亮但暂时用不上的运行时。

### 已完成基线

| 能力 | 当前状态 | 说明 |
|------|----------|------|
| `repo_analyzer` 扫描 Gitea | 已完成 | 支持全仓库扫描、指定仓库 detail、AI/非 AI 汇总 |
| 项目上下文文档读取 | 已完成 | 已读取 `项目背景.md`、`项目进度.md`、`项目目的.md`、`README.md` 并注入分析上下文 |
| `--write-memory` | 已完成 | 已能将扫描证据写入 `org_memory` SQLite |
| `agent_engine` 骨架 | 已完成 | 已有 schema、mode、router、risk、chains 空壳 |
| 组织记忆规则提取 | 已完成 | 已有规则版 FactExtractor，便于测试和稳定落库 |

### Iteration 0（优先）：组织记忆闭环

| 事项 | 工作量 | 说明 |
|------|--------|------|
| P0: 增加 `repo_analyzer --use-memory` | 1~1.5d | 分析前读取 org_memory 中的历史事实、项目状态、人员贡献，注入日报和 detail prompt |
| P0: 报告体现记忆引用 | 0.5d | 在报告中增加简短的“记忆参考/历史依据”，或者静默用于 AI prompt 并在 metadata 中记录 |
| P0: `--use-memory + --write-memory` 闭环测试 | 0.5d | 第一次写入，第二次读取，验证不会重复污染事实 |

推荐目标命令：

```bash
python -m repo_analyzer.main --all-repos --days 1 --use-memory --write-memory --output reports/gitea-daily.md
```

### Iteration 1：agent_engine 接入真实模型

| 事项 | 工作量 | 说明 |
|------|--------|------|
| P1: 裁剪复用 ModelProvider | 1~1.5d | 保留 OpenAI-compatible chat completions、timeout、tool_calls 基础结构，适配现有 `config.json` |
| P1: 实现 `personal_brief.py` chain | 1~1.5d | 接收 AgentRequest，组织 prompt，调用模型，返回 AgentResponse |
| P1: 实现 `management_brief.py` chain | 1~1.5d | 读取 org_memory / repo_analyzer 数据，生成管理者简报 |
| P1: Orchestrator 调度 chain | 0.5~1d | 从“规则路由 + 占位回答”升级为“规则路由 + 对应 chain 生成回答” |

### Iteration 2：轻量工具协议 + 内部工具

| 事项 | 工作量 | 说明 |
|------|--------|------|
| P1: 复用 ToolResult / PermissionDecision | 0.5d | 只复用结构，不引入完整 Skill 插件系统 |
| P1: 设计 agentos 内部 ToolProtocol | 1~1.5d | 支持输入校验、权限判断、执行、风险描述 |
| P1: 首批内部工具 | 1~1.5d | `gitea.query`、`org_memory.search`、`repo_analyzer.detail` |
| P2: chain 集成工具调用 | 1d | management_brief 能通过工具获取实时数据和记忆证据 |

### Iteration 3（后续）：EventBus、策略体系、个人记忆层

| 事项 | 工作量 | 说明 |
|------|--------|------|
| EventBus 集成 | 0.5d | 用于路由、工具调用、风险判断、记忆读写等事件审计 |
| PolicyGuard 参考实现 | 1.5~2.5d | 不直接复用 chatbot 版本，但参考 PolicyDecision 结构，和 AccessContext / 审批队列对齐 |
| 个人工作记忆层 | 3~5d | 参考 chatbot 的 session/midterm/longterm 思路，但重新适配 agentos 的用户、角色、审计上下文 |
| 同事接口对齐 | 待定 | 同步 AgentRequest/AgentResponse schema 给 Dev1/Dev3/Dev4 |

### 总体时间评估

| 范围 | 预计时间 | 可交付结果 |
|------|----------|------------|
| 最小可演示闭环 | 4~6 个工作日 | `repo_analyzer` 能读写组织记忆，报告使用历史事实和项目上下文 |
| Iteration 1 + Iteration 2 | 7~10 个工作日 | `agent_engine` 有真实模型调用、可运行 chain、内部工具协议 |
| 含 Iteration 3 | 12~18 个工作日 | 具备事件审计、策略判断、个人记忆补充层 |

---

## 五、可复用 / 裁剪复用的文件

```
# 零依赖工具 — 直接复制，不改逻辑
chatbot/src/common/event_bus.py           → agentos-product/src/common/event_bus.py
chatbot/src/common/sanitize.py            → agentos-product/src/common/sanitize.py

# 模型接口 + 适配器 — 接口可复用，adapter 需要裁剪
chatbot/src/runtime_module/model_provider.py  → agentos-product/src/agent_engine/model_client.py
chatbot/src/chat_module/adapters.py           → agentos-product/src/agent_engine/adapters.py

# 工具协议数据结构 — 结构可复用，权限逻辑需适配 AccessContext
chatbot/src/runtime_module/tool_protocol.py   → agentos-product/src/agent_engine/tool_result.py

# 工具函数
chatbot/src/memory_module/token_counter.py    → agentos-product/src/common/token_counter.py
```

---

## 六、不变的部分

下列模块无需从 chatbot 复用，保持现有实现：

| 模块 | 原因 |
|------|------|
| `agent_engine/schemas.py` | 已经定义完整，且是跨角色对齐的契约 |
| `agent_engine/modes.py` | 7 种模式已经覆盖产品需求 |
| `agent_engine/router.py` | 规则路由在 MVP 阶段够用 |
| `agent_engine/risk.py` | RiskClassifier 设计合理，增强而非替换 |
| `org_memory/` 全部 | 组织级记忆系统已经比 chatbot 的更成熟，专注补充个人层 |
| `commit_guide/` | 已完成，无需改动 |
| `repo_analyzer/` | 项目上下文读取已完成，下一步只补 `--use-memory` 闭环，不改整体架构 |

---

## 七、验证方式

1. **组织记忆闭环**: 第一次运行 `--write-memory` 写入事实，第二次运行 `--use-memory` 能读取历史事实并影响报告上下文
2. **repo_analyzer**: 全仓库扫描报告继续包含项目背景、项目进度、README 等项目上下文
3. **模型调用**: `personal_brief` chain 能输出真实 AI 回答而非硬编码字符串
4. **工具调用**: chain 内调 Gitea API / org_memory 获取数据并正确渲染
5. **EventBus**: 订阅路由事件并打印，确认事件透传正常
6. **现有测试**: `python -m pytest tests/ -v` 或至少 `python -m unittest discover tests/agent_engine_tests/` 保持绿
