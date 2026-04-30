# DailySync 管理者辅助智能体平台设计文档（修订版）

> 本文档基于《离线系统级智能体平台设计文档》修订，并结合 DailySync 当前讨论结论进行收敛。  
> 修订方向：保留原方案中 Kernel / Runtime / Registry / Memory / Skill / Model / Policy 等平台底座，但将目标从“泛系统级智能体平台”收敛为“面向管理者的 DailySync 工作同步智能体”。

---

## 1. 文档目标

本文档用于定义一个**本地部署、可离线运行、以 Gitea 工作事件为核心数据源、具备长期记忆能力、面向管理者服务的 DailySync 智能体平台**。

DailySync 的定位不是普通聊天机器人，也不是员工监控系统，而是：

> 一个管理者专属的工作同步服务员。它能够从 Gitea、员工补充清单、PR / Issue / Review 等已有工作系统中提取工作事件，结合记忆系统生成日报、周报、风险提醒，并支持管理者对话式查询。

本文档重点定义：

- DailySync 的本地部署架构
- Gitea 数据接入与 Evidence Pack 生成
- 身份映射与噪声过滤
- 日报 / 周报生成任务
- 管理者智能体与子智能体分工
- 记忆系统如何复用现有 `memory_module`
- 员工工作公开与隐私边界
- Policy / 系统规则 / 禁止项
- 卡片推送与前端渲染
- 后续扩展路线

---

## 2. 与原方案相比的核心修改

原方案的底层架构方向是正确的，尤其是以下部分应保留：

- Kernel 管控制，不管业务
- Runtime 管执行，不管存储细节
- Registry 管装配，不管行为逻辑
- Skill 是一等能力对象，必须强类型化
- Memory 是独立服务，不嵌入 agent 类
- Action Adapter 是系统操控唯一出口
- Policy 是硬约束，不依赖 prompt
- Supervisor 负责分配，不负责所有执行

但结合 DailySync 的实际目标，需要做以下修改：

| 原方案 | 修订建议 |
|---|---|
| 泛系统级智能体平台 | 收敛为 DailySync 管理者辅助智能体平台 |
| 强调系统 / 软件操控 | 系统操控降级为辅助能力，核心是工作事件分析与报告生成 |
| Memory Service 中包含 Semantic Memory / 知识层 | 改为“记忆系统”，不称为知识库；长期记忆只存稳定上下文 |
| 非目标包含聊天软件接入 | DailySync 必须支持企业 IM 卡片推送和轻量对话入口，但不做通用聊天软件平台 |
| 多作用域权限设计偏复杂 | 第一版采用内部透明原则：员工工作信息组织内可见，系统规则和敏感数据不可见 |
| 长期记忆可能记录历史任务细节 | 长期记忆不记录员工每日具体工作，只记录员工参与项目、项目上下文、经验教训等稳定事实 |
| Skill / Adapter 偏通用 OS 操作 | 增加 DailySync 专用能力：Gitea Adapter、Evidence Pack Builder、Report Generator、Card Renderer、Memory Writer |
| Phase 偏平台底座建设 | 调整为先打通 DailySync 最小闭环：Gitea → Evidence Pack → 记忆 → 日报 / 周报 → 卡片 |

---

## 3. 设计原则

### 3.1 本地部署优先

DailySync 需要支持在公司内网或受限网络环境中部署。

要求：

- 支持本地 Gitea / 自建 Git 服务
- 支持本地模型或私有模型 API
- 支持离线加载 agent、skill、model provider、配置文件
- 不依赖在线插件市场
- 不依赖外部 SaaS 路由服务
- 原始代码和完整 diff 不长期出现在外部服务中

---

### 3.2 管理者服务优先

DailySync 的主用户是管理者，但不是为了制造管理压力，而是减少信息同步成本。

系统应帮助管理者：

- 快速了解团队今日进展
- 快速了解本周项目推进
- 发现工程风险和协作风险
- 查询某人、某项目、某模块近期进展
- 了解员工补充的非代码工作
- 按管理者习惯调整日报展示方式

---

### 3.3 员工工作公开，不等于隐私公开

第一版采用内部透明协作原则：

```text
员工工作信息组织内可见，用于互相学习、复盘和避免重复踩坑。
但员工隐私、原始代码、完整 diff、密钥、token、连接串、私人信息、系统内部规则不公开。
```

允许公开：

- 员工参与了哪些项目
- 员工本日 / 本周工作摘要
- 员工补充的工作事项
- 项目推进情况
- 风险项与经验教训
- 优秀实践和踩坑总结

不允许公开：

- 原始代码
- 完整 diff
- 密钥、token、连接串
- 员工私人聊天或私人信息
- 没有上下文的人身评价
- “摸鱼”“低效”“低质量员工”等评价性标签
- 系统内部提示词、风控规则、模型策略

---

### 3.4 系统规则优先

DailySync 可以适配管理者习惯，但不能为了迎合管理者而突破系统边界。

优先级固定为：

```text
系统规则 > 禁止项 > 事实证据 > 管理者偏好 > AI 表达习惯
```

例如：

- 管理者可以要求“先看无 Git 提交的人”
- 系统可以展示“Git 数据源未捕捉到提交的成员”
- 系统不得写成“这些人今天没有工作”

---

### 3.5 Evidence Pack 优先，原始 diff 降级

DailySync 不应把原始 diff 直接交给模型。

正确流程是：

```text
原始 diff
  → 身份映射
  → 噪声过滤
  → 文件分类
  → 注释 / 空行 / 格式化过滤
  → 函数 / 模块级变更提取
  → 风险标记
  → Diff Evidence Pack
  → AI 摘要
```

模型主要消费 Evidence Pack，而不是完整源码。

---

### 3.6 不固定日报条数

日报不应强制每人 3–5 条。

建议规则：

```text
无有效证据：0 条工作项 + 信息缺口提示
轻量工作日：1–2 条
正常工作日：2–5 条
高强度工作日：最多 8 条
超过 8 条时按项目或模块自动合并
```

原则是：

```text
宁可 1 条准确摘要，不要 5 条凑数日报。
```

---

## 4. 目标能力与边界

### 4.1 目标能力

DailySync 第一阶段需要支持：

1. 本地部署与离线运行
2. Gitea / Git 数据接入
3. Gitea 官方能力复用：API、Tea CLI、Gitea MCP 或本地 git 命令
4. 员工身份映射
5. 噪声过滤
6. Diff Evidence Pack 生成
7. PR / Issue / Review 关联
8. 员工每日工作清单补充
9. 工作日 21:00 生成日报
10. 每周末 18:00 生成周总结
11. 日报 / 周报卡片推送
12. 前端模板渲染卡片，可选导出图片
13. 管理者对话式查询
14. 管理者偏好记忆
15. 员工项目关系记忆
16. 项目上下文记忆
17. 经验教训沉淀
18. Policy / 禁止项 / 审计

---

### 4.2 当前非目标

第一版暂不覆盖：

- 屏幕监控
- 键盘监控
- 摄像头或行为监控
- 员工个人隐私分析
- 原始代码长期保存
- 完整 diff 长期保存
- 固定代码行数 KPI
- 对员工进行人格、态度、绩效式评价
- 复杂多租户 SaaS 权限体系
- 多节点分布式调度
- 在线插件市场
- fork Gitea 并深度修改源码
- 让日报 agent 拥有 Gitea 写操作权限

说明：

- 第一版不建议 fork Gitea。
- Gitea 官方 API / Tea CLI / Gitea MCP / 本地 git 命令足以承担第一版数据入口。
- 如后续发现 Gitea API 性能、权限或数据粒度存在瓶颈，再考虑 fork 或新增 Gitea 专用接口。

---

## 5. 总体架构

### 5.1 逻辑视图

```text
企业 IM / Web 管理台 / CLI / 定时任务
        |
        v
+--------------------------------------------------+
|             DailySync Interface Layer            |
|  IM Bot / Card / Web UI / Supplement Form / API  |
+--------------------------------------------------+
        |
        v
+--------------------------------------------------+
|              DailySync Domain Layer              |
| Gitea Adapter / Identity Mapper / Noise Filter   |
| Evidence Pack Builder / Report Job / Card Render |
| Manual Supplement / Manager Query / Memory Writer|
+--------------------------------------------------+
        |
        v
+--------------------------------------------------+
|                Agent Runtime Kernel              |
| Kernel / Task / Session / Event / Registry       |
| Runtime / Delegation / Skill / Model / Policy    |
+--------------------------------------------------+
        |
        v
+--------------------------------------------------+
|               Capability & Provider Layer        |
| Memory Module / Model Provider / Gitea Tools     |
| IM Adapter / Storage / Audit / Action Adapter    |
+--------------------------------------------------+
        |
        v
+--------------------------------------------------+
|                  Backend Systems                 |
| Gitea / Git / PostgreSQL / Redis / Local LLM     |
| 企业微信 / 飞书 / 钉钉 / 本地文件系统             |
+--------------------------------------------------+
```

---

### 5.2 分层说明

#### DailySync Interface Layer

负责承接：

- 管理者查看日报 / 周报
- 企业 IM 卡片推送
- 员工每日工作清单补充
- 管理者对话式查询
- 管理后台配置

第一版可支持：

```text
企业 IM 卡片 + Web 管理台 + 简单 API
```

不需要一开始做复杂聊天软件生态。

---

#### DailySync Domain Layer

这是原方案缺少、但 DailySync 必须新增的一层。

职责：

- 员工身份映射
- Gitea 数据采集
- commit / PR / Issue / Review 关联
- 噪声过滤
- Diff Evidence Pack 构建
- 日报 / 周报任务编排
- 员工补充清单合并
- 卡片渲染
- 记忆写入与检索
- 管理者偏好适配

该层不应该塞进 Kernel。

---

#### Agent Runtime Kernel

保留原方案的底层能力：

- Kernel
- Task Manager
- Session Manager
- Event Bus
- Registry System
- Agent Runtime
- Delegation Manager
- Skill Runtime
- Model Provider
- Memory Service
- Policy & Security
- Audit & Observability

Kernel 不写 DailySync 业务逻辑，只负责调度、生命周期和模块装配。

---

#### Capability & Provider Layer

负责具体能力接入：

- Gitea API / Tea CLI / Gitea MCP / 本地 git 命令
- 现有 `memory_module`
- 模型 API
- IM 推送适配器
- 卡片渲染器
- 数据库
- 审计日志

---

## 6. 核心模块修订

### 6.1 Kernel 模块

保留原方案定义。

修订要求：

- Kernel 不出现 DailySync 业务逻辑
- Kernel 不写死 Gitea、日报、周报等概念
- Kernel 只管理系统生命周期、依赖注入、事件总线、任务管理、注册表
- DailySync 业务能力通过 package / service / skill 注册进入系统

新增建议：

```text
SystemContext 增加：
- dailysync_service
- report_scheduler
- card_renderer
- im_adapter_registry
```

但这些字段也可以通过 Registry 获取，避免 Kernel 强耦合。

---

### 6.2 Task Manager 模块

保留原方案中的 Task 生命周期。

DailySync 新增任务类型：

```text
gitea.scan_daily_activity
identity.resolve_author
noise.filter_commits
diff.build_evidence_pack
report.generate_daily
report.generate_weekly
report.merge_manual_supplement
card.render_report
im.push_card
manager.query
memory.write_daily_context
memory.distill_longterm
policy.review_report
```

日报任务示例：

```json
{
  "task_id": "task_daily_backend_20260430",
  "task_type": "report.generate_daily",
  "team_id": "backend",
  "date": "2026-04-30",
  "status": "running",
  "metadata": {
    "schedule": "weekday_21_00",
    "source": "system_scheduler"
  }
}
```

设计要求：

- 每次日报 / 周报生成必须有 task_id
- Gitea 扫描、Evidence Pack、报告生成、卡片推送都要形成子任务
- 支持失败重试和补发
- 支持按 task 回放和审计

---

### 6.3 Session Manager 模块

原方案中“Session 不等于长期记忆”的判断保留。

DailySync 中建议拆为两类 session：

```text
manager_chat_session
- 管理者主动提问
- 适合保留对话上下文
- 可记录管理者偏好线索

report_generation_session
- 系统自动生成日报 / 周报
- 不一定需要长期聊天上下文
- 更适合作为后台任务上下文
```

Session 中只保存近期上下文，不承担长期记忆。

---

### 6.4 Event Bus 模块

保留原方案事件总线。

DailySync 新增事件：

```text
gitea.activity_scanned
identity.mapped
noise.filtered
evidence_pack.created
manual_supplement.submitted
report.daily_generated
report.weekly_generated
report.card_rendered
report.card_pushed
manager.feedback_received
memory.longterm_written
policy.report_blocked
```

事件设计要求：

- 事件对象必须结构化
- 事件中不得包含完整原始 diff
- 敏感信息不得进入事件日志
- 核心事件必须可追踪、可回放

---

### 6.5 Registry System 模块

保留原方案 Registry。

DailySync 需要注册的能力包括：

```text
Agents:
- dailysync_supervisor
- report_generator_agent
- code_change_analyst_agent
- memory_distill_agent
- policy_review_agent
- manager_query_agent

Skills:
- gitea.list_commits
- gitea.list_pull_requests
- gitea.list_issues
- git.get_diff
- diff.build_evidence_pack
- report.generate_daily_json
- report.generate_weekly_json
- card.render_html
- card.export_image
- im.push_message
- memory.search
- memory.write
- manual_supplement.add

Adapters:
- GiteaAdapter
- TeaCLIAdapter
- GiteaMCPAdapter
- LocalGitAdapter
- FeishuAdapter
- WeComAdapter
- DingTalkAdapter
```

注意：

- Gitea MCP 只作为底层工具之一
- 日报 agent 不应直接拥有 Gitea 写操作工具
- 对上层 agent 暴露 DailySync 领域工具，而不是裸露全部 Gitea 能力

---

### 6.6 Agent Runtime 模块

保留原方案执行循环：

```text
Build Context → Plan → Decide → Act → Observe → Reflect → Continue / Stop
```

DailySync 中建议 agent 分工如下。

#### 6.6.1 dailysync_supervisor

职责：

- 理解管理者请求
- 判断是日报、周报、查询、补充、配置还是反馈
- 分配给合适子 agent 或 skill
- 汇总结果
- 保证输出符合系统规则

---

#### 6.6.2 report_generator_agent

职责：

- 根据 Evidence Pack、员工补充、记忆上下文生成日报 / 周报
- 输出结构化 JSON
- 不直接输出卡片图片
- 不直接读取完整源码

---

#### 6.6.3 code_change_analyst_agent

职责：

- 分析 Evidence Pack
- 判断变更类型：feature / bugfix / refactor / test / config / dependency
- 识别工程风险：认证、支付、权限、数据库、配置、依赖等
- 不保存完整 diff

---

#### 6.6.4 memory_distill_agent

职责：

- 从中期记忆和业务记录中提炼长期记忆
- 只提炼稳定事实
- 不把员工每日具体工作写入长期记忆

---

#### 6.6.5 policy_review_agent

职责：

- 检查日报 / 周报是否违反系统规则
- 检查是否包含原始代码、完整 diff、敏感信息
- 检查是否存在对员工的人格化负面评价
- 检查“无 Git 提交”是否被误写成“无工作”

---

#### 6.6.6 manager_query_agent

职责：

- 回答管理者对人、项目、模块、风险、周进展的查询
- 优先从日报 / 周报 / 记忆系统 / 业务记录检索
- 默认不实时读取完整 diff

---

### 6.7 Delegation Manager 模块

保留原方案的三种委派模式：

- Direct Delegation
- Pipeline Delegation
- Review Delegation

DailySync 常用流水线：

```text
report.generate_daily
  → gitea.scan_daily_activity
  → identity.resolve_author
  → noise.filter_commits
  → diff.build_evidence_pack
  → memory.search_context
  → report_generator_agent
  → policy_review_agent
  → card.render_report
  → im.push_card
  → memory.write_daily_context
```

第一版仍不建议：

- 多智能体自由讨论
- 无限递归委派
- 无约束广播式协作

---

### 6.8 Skill Runtime 模块

保留原方案中的强类型 Skill 设计。

DailySync 的 skill 必须满足：

- 输入输出有 schema
- 执行前经过 PolicyGuard
- 输出结构化
- 不返回完整原始 diff
- 不返回源码全文
- 不执行任意 shell

#### 6.8.1 DailySync Skill 示例

```yaml
id: dailysync.diff.build_evidence_pack
name: Build Diff Evidence Pack
version: 1.0.0
description: Build low-token structured evidence from git diff.
entrypoint: executor:BuildEvidencePackSkill
input_schema:
  type: object
  properties:
    repo_id:
      type: string
    commit_sha:
      type: string
    options:
      type: object
  required: [repo_id, commit_sha]
output_schema:
  type: object
  properties:
    evidence_pack:
      type: object
permissions:
  - git.diff.read
  - evidence_pack.write
timeout: 30
dangerous: false
dependencies: []
```

---

### 6.9 Model Provider 模块

保留原方案。

DailySync 对模型输出有额外要求：

- 日报必须输出 JSON
- 周报必须输出 JSON
- 风险项必须结构化
- 每条摘要必须标明来源类型：git / pr / issue / supplement / memory
- 模型不得输出完整代码
- 模型不得臆断员工未工作
- 模型不得生成对员工的人格评价

建议 ModelRequest 增加：

```python
metadata = {
    "task_type": "report.generate_daily",
    "team_id": "backend",
    "date": "2026-04-30",
    "policy_profile": "dailysync_report_policy",
}
```

---

### 6.10 Memory Service 模块

原方案中的 Memory Service 需要重点修改。

DailySync 不应把这里称为“知识库”，而应称为：

```text
记忆系统 / Memory System
```

当前已有 `memory_module`，它已经具备三层记忆结构：

```text
Session Memory：会话短期上下文
Midterm Memory：每日 / 近期记忆
Longterm Memory：长期稳定记忆
```

因此 DailySync 不需要重新实现一套知识库，而应复用现有记忆模块，并新增 DailySync 领域封装。

---

#### 6.10.1 记忆分层

DailySync 采用三层记忆 + 业务记录的结构。

```text
Session Memory
- 管理者当前对话上下文
- 当前查询任务上下文
- 临时工具结果摘要

Midterm Memory
- 当天日报摘要
- 员工补充清单
- 当日风险信号
- 本周临时项目进展
- 管理者近期反馈

Longterm Memory
- 管理者偏好
- 系统规则
- 禁止项
- 员工项目关系
- 团队上下文
- 项目上下文
- 仓库模块映射
- 经验教训
- 稳定事实

Business Records
- daily_reports
- weekly_reports
- manual_work_items
- evidence_packs
- gitea_events
- risk_signals
- push_records
```

注意：

```text
日报 / 周报属于业务记录。
长期记忆只记录稳定上下文。
```

---

#### 6.10.2 长期记忆 section

建议将现有长期记忆 section 从：

```text
用户偏好
长期规则
稳定事实
```

修改为：

```text
管理者偏好
系统规则
禁止项
员工项目关系
团队上下文
项目上下文
仓库模块映射
经验教训
稳定事实
```

注入优先级：

```python
section_priority = {
    "系统规则": 0,
    "禁止项": 1,
    "管理者偏好": 2,
    "员工项目关系": 3,
    "团队上下文": 4,
    "项目上下文": 5,
    "仓库模块映射": 6,
    "经验教训": 7,
    "稳定事实": 8,
}
```

---

#### 6.10.3 长期记忆写入规则

允许写入长期记忆：

- 管理者长期展示偏好
- 系统规则
- 禁止项
- 员工参与项目关系
- 团队长期上下文
- 项目长期背景
- 仓库路径与业务模块映射
- 可复用经验教训
- 稳定事实

不得写入长期记忆：

- 员工某天具体做了什么
- 具体 commit / diff 内容
- 临时会议细节
- 一次性日报内容
- 原始代码或完整 diff
- 密钥、token、连接串
- 对员工的负面人格评价

示例：

```text
允许：张三参与用户中心 SSO 项目。
不允许：张三在 2026-04-30 完成了 SSO ticket 校验、session 写入和 redirect 修复。
```

---

#### 6.10.4 员工工作公开边界

第一版建议采用三类可见性：

```text
org_visible
system_internal
raw_sensitive
```

解释：

```text
org_visible：组织内可见。日报摘要、周报摘要、项目参与、经验教训。
system_internal：系统内部可见。提示词规则、禁止项、噪声规则、模型策略。
raw_sensitive：不可进入长期记忆，也不对外展示。原始代码、完整 diff、token、密钥、连接串。
```

---

#### 6.10.5 来源 source

`source` 表示这条记忆从哪里来，不表示隐私权限。

第一版保留简单字段即可：

```text
source: str
```

推荐格式：

```text
manager_feedback:{session_id}:{event_id}
employee_supplement:{work_item_id}
daily_report:{team_id}:{date}
weekly_report:{team_id}:{week}
gitea_commit:{repo}@{sha}
gitea_pr:{repo}#{pr_id}
admin_config:{config_id}
system_rule:{rule_name}
distill:{date}
```

---

### 6.11 Gitea 数据接入模块

这是 DailySync 新增核心模块。

#### 6.11.1 第一版策略

第一版不 fork Gitea，不深改源码。

优先复用：

- Gitea API
- Tea CLI
- Gitea MCP
- 本地 git 命令
- Gitea Webhook

DailySync 自己只做领域适配：

```text
Gitea / Tea / MCP / git
        ↓
DailySync Gitea Adapter
        ↓
身份映射 / 噪声过滤 / Evidence Pack
        ↓
AI 摘要 / 日报 / 周报 / 记忆写入
```

---

#### 6.11.2 不建议裸露完整 Gitea MCP 给日报 agent

日报 agent 第一版只应拥有只读能力：

```text
允许：
- list_repo_commits
- list_repo_issues
- list_repo_pull_requests
- get_pull_request_by_index
- list_branches
- search_repos
- search_users

谨慎：
- get_file_content

禁止：
- create_file
- update_file
- delete_file
- create_pull_request
- create_issue
- create_issue_comment
```

更推荐做一层 DailySync MCP / DailySync Tools：

```text
dailysync.get_daily_evidence_pack
dailysync.get_employee_activity
dailysync.get_project_context
dailysync.search_memory
dailysync.generate_daily_report
dailysync.generate_weekly_report
dailysync.add_manual_work_item
```

---

### 6.12 Identity Mapper 模块

身份映射应前置，而不是采集后才修正。

优先级：

```text
1. Gitea user_id 精确匹配
2. commit email 匹配员工企业邮箱
3. commit email 匹配员工绑定邮箱
4. Gitea username 匹配员工账号
5. 员工手动认领历史 commit email
6. 管理员手动修正
```

未识别身份进入待确认池：

```json
{
  "repo": "backend-service",
  "author": "zhangsan-mbp",
  "email": "zs.local@example.com",
  "commits": 4,
  "suggested_employee": "张三",
  "confidence": 0.72
}
```

---

### 6.13 Noise Filter 模块

噪声过滤同样应前置。

分三层：

#### 账号级过滤

```text
bot 账号
CI 账号
release 账号
部署账号
自动同步账号
```

#### commit 级过滤 / 标记

```text
merge commit
revert commit
release commit
auto format commit
dependency only commit
generated files commit
message 过短 commit
一次性跨太多模块 commit
```

#### file / diff 级过滤

```text
dist/
build/
target/
node_modules/
vendor/
coverage/
*.min.js
*.map
自动生成 protobuf
自动生成 ORM 文件
图片、字体、压缩包、二进制文件
```

lock 文件不直接删除，应降权：

```text
package.json + lock 文件一起变更：保留
只有 lock 文件变化：降权
依赖版本涉及安全修复：保留并标风险
```

---

### 6.14 Diff Evidence Pack 模块

Evidence Pack 是 DailySync 的质量核心。

示例：

```json
{
  "commit": {
    "sha": "abc123",
    "message": "feat: support sso login",
    "author": "张三",
    "time": "2026-04-30T16:20:00+08:00"
  },
  "repo": "user-center",
  "branch": "main",
  "files": [
    {
      "path": "src/auth/sso_service.ts",
      "category": "auth",
      "language": "typescript",
      "change_type": "feature",
      "effective_added": 82,
      "effective_deleted": 15,
      "changed_symbols": [
        "validateSsoTicket",
        "bindExternalUser",
        "createLoginSession"
      ],
      "logic_changes": [
        "新增 SSO ticket 校验逻辑",
        "新增外部用户与本地用户绑定逻辑",
        "登录成功后写入 session"
      ],
      "ignored_changes": [
        "日志文案调整",
        "空行变化"
      ],
      "risk_flags": [
        "authentication_flow",
        "session_management"
      ]
    }
  ]
}
```

Evidence Pack 不应包含完整源码。

---

### 6.15 Report Job 模块

DailySync 新增独立报告任务模块。

#### 6.15.1 日报调度

默认：

```text
工作日 20:30：提醒员工补充今日工作清单
工作日 20:50：汇总 Git + PR + Issue + 员工补充
工作日 21:00：生成并推送日报
```

#### 6.15.2 周报调度

默认：

```text
每周末 18:00：生成团队周总结
```

如果企业采用大小周或周六工作制，则由企业日历配置决定具体执行日。

---

#### 6.15.3 日报输出规则

- 不固定条数
- 不凑内容
- 同一需求多个 commit 合并
- 不同项目 / 模块拆开
- Git 无提交不得推断为无工作
- 员工补充必须标明来源
- 风险项优先展示
- 不输出完整代码
- 不输出人格评价

日报 JSON 示例：

```json
{
  "employee": "张三",
  "date": "2026-04-30",
  "source_summary": {
    "git_commits": 5,
    "pull_requests": 1,
    "issues": 1,
    "manual_supplements": 0
  },
  "summary_items": [
    {
      "title": "推进用户中心 SSO 登录接入",
      "content": "完成 ticket 校验、外部用户绑定和登录态写入逻辑。",
      "type": "feature",
      "sources": ["git", "pull_request"],
      "evidence": ["user-center@abc123", "PR#128"],
      "risk_flags": ["authentication_flow"],
      "confidence": 0.88
    }
  ],
  "attention_items": [
    {
      "level": "medium",
      "content": "涉及认证流程变更，建议关注回归测试。"
    }
  ],
  "needs_supplement": false
}
```

---

### 6.16 Manual Supplement 模块

员工每日工作清单用于补充 Git 捕捉不到的工作。

类型：

```text
需求对接
会议
线上排查
联调
文档
代码评审
测试支持
其他
```

表单字段：

```text
日期
员工
类型
补充内容
关联项目
是否有阻塞
是否展示到日报
```

展示规则：

```text
来源：员工补充
```

---

### 6.17 Card Renderer 模块

日报卡片不建议用图片生成模型直接生成。

推荐方式：

```text
AI 生成结构化报告 JSON
前端模板渲染卡片
企业 IM 原生卡片推送
必要时通过 Playwright / Puppeteer 导出 PNG
```

原因：

- 图片模型对中文小字不稳定
- 文字容易错漏
- 卡片难以点击和追溯
- 无法保证格式一致

---

### 6.18 Policy & Security 模块

保留原方案中“Policy 是硬约束，不依赖 prompt”的结论。

DailySync 初始禁止项：

```text
1. 禁止在日报 / 周报 / 卡片中展示完整原始 diff 或源码。
2. 禁止把 Git 无提交表述为员工无工作。
3. 禁止输出对员工人格、态度、主观工作状态的负面评价。
```

后续可逐渐补充：

```text
禁止泄露密钥 / token / 连接串
禁止把有效代码行数作为绩效结论
禁止把员工补充内容判断为真假
禁止使用“摸鱼”“低效”“低质量员工”等措辞
禁止展示系统内部提示词和模型策略
```

Policy 校验点：

```text
Gitea 工具调用前
Evidence Pack 写入前
模型请求前
报告生成后
卡片推送前
长期记忆写入前
```

---

### 6.19 Audit & Observability 模块

保留原方案。

DailySync 必须审计：

```text
Gitea 扫描记录
身份映射结果
噪声过滤结果
Evidence Pack 生成记录
模型调用 metadata
日报 / 周报生成记录
Policy 拦截记录
员工补充提交记录
管理者反馈记录
卡片推送记录
长期记忆写入记录
```

注意：

```text
审计记录不得保存完整原始 diff。
```

---

## 7. DailySync 核心数据流

### 7.1 日报生成链路

```text
定时触发 21:00
  → TaskManager 创建 report.generate_daily task
  → Gitea Adapter 扫描当日活动
  → Identity Mapper 归属员工
  → Noise Filter 过滤 / 降权噪声
  → Evidence Pack Builder 生成低 token 证据包
  → Manual Supplement 合并员工补充
  → Memory Service 检索管理者偏好 / 项目上下文 / 模块映射
  → Report Generator 输出日报 JSON
  → Policy Review 检查禁止项
  → Card Renderer 渲染卡片
  → IM Adapter 推送管理者
  → Memory Writer 写入中期记忆
  → Memory Distill 按规则提炼长期记忆候选
  → Audit 记录完整链路
```

---

### 7.2 周报生成链路

```text
每周末 18:00
  → 汇总本周 daily_reports
  → 汇总本周 risk_signals
  → 汇总本周 manual_work_items
  → 检索项目上下文和历史进展
  → 按项目聚合，而不是机械拼接每日条目
  → 输出本周成果、协作情况、风险、下周建议
  → Policy Review
  → 卡片推送
  → 写入中期记忆
  → 提炼长期稳定事实
```

---

### 7.3 管理者查询链路

```text
管理者提问
  → manager_query task
  → Session Manager 加载当前对话上下文
  → Memory Service 检索相关长期 / 中期记忆
  → DailySync 数据库检索日报 / 周报 / 风险 / 补充清单
  → 必要时查询 Gitea metadata
  → 默认不实时读取完整 diff
  → 生成回答
  → Policy Review
  → 返回管理者
```

---

## 8. 推荐数据表

### 8.1 DailySync 业务表

```text
employees
- id
- name
- email
- department
- status

git_identities
- id
- employee_id
- platform
- username
- commit_email
- confidence
- confirmed_by

repositories
- id
- platform
- name
- url
- default_branch
- status

gitea_events
- id
- repo_id
- event_type
- event_ref
- author_identity
- event_time
- payload_summary

evidence_packs
- id
- repo_id
- commit_sha
- employee_id
- date
- evidence_json
- risk_flags
- created_at

manual_work_items
- id
- employee_id
- date
- category
- content
- project_id
- blocked
- visible
- created_at

daily_reports
- id
- employee_id
- team_id
- date
- report_json
- report_markdown
- generated_at
- status

weekly_reports
- id
- team_id
- week_start
- week_end
- report_json
- report_markdown
- generated_at
- status

risk_signals
- id
- date
- team_id
- project_id
- repo_id
- employee_id
- risk_type
- severity
- content
- status

push_records
- id
- report_id
- report_type
- channel
- target
- pushed_at
- status
```

---

### 8.2 记忆系统

现有 `memory_module` 继续承担：

```text
sessions/
memory/YYYY-MM-DD.md
MEMORY.md
vector_store
memory eval log
```

DailySync 可新增领域服务：

```text
src/dailysync_module/memory_service.py
```

不要直接在业务代码中到处调用底层 `MemoryModule`。

---

## 9. 推荐项目目录结构

```text
src/
  core/
    config.py
    events.py
    exceptions.py
    types.py

  kernel/
    system_kernel.py
    system_context.py
    boot.py

  tasks/
    task_manager.py
    task_models.py
    task_store.py

  runtime/
    agent_runner.py
    context_builder.py
    planner.py
    executor.py
    reflection.py
    delegation_manager.py

  registry/
    agent_registry.py
    skill_registry.py
    model_registry.py
    adapter_registry.py
    package_registry.py

  memory_module/
    # 复用现有三层记忆模块

  dailysync_module/
    __init__.py
    service.py
    gitea_adapter.py
    identity_mapper.py
    noise_filter.py
    evidence_pack.py
    report_job.py
    report_generator.py
    card_renderer.py
    manual_supplement.py
    manager_query.py
    memory_service.py
    memory_prompts.py
    policy_rules.py
    audit_writer.py

  models/
    provider_base.py
    provider_manager.py
    request_response.py
    providers/

  skills/
    skill_base.py
    skill_loader.py
    skill_validator.py
    skill_executor.py
    dailysync_skills/

  adapters/
    gitea_api_adapter.py
    tea_cli_adapter.py
    gitea_mcp_adapter.py
    local_git_adapter.py
    feishu_adapter.py
    wecom_adapter.py
    dingtalk_adapter.py

  policy/
    permission_policy.py
    execution_policy.py
    report_policy.py
    memory_policy.py
    policy_guard.py

  audit/
    audit_logger.py
    playback.py

  api/
    server.py
    routes/

  ui/
    web_admin/
    card_templates/
    cli.py

packages/
  agents/
  skills/

tests/
```

---

## 10. 现有 memory_module 最小改造建议

### 10.1 扩展长期记忆 section

将 `_VALID_SECTIONS` 从：

```python
_VALID_SECTIONS = {"用户偏好", "长期规则", "稳定事实"}
```

修改为：

```python
_VALID_SECTIONS = {
    "管理者偏好",
    "系统规则",
    "禁止项",
    "员工项目关系",
    "团队上下文",
    "项目上下文",
    "仓库模块映射",
    "经验教训",
    "稳定事实",
}
```

---

### 10.2 修改长期记忆提炼 prompt

新增规则：

```text
长期记忆只允许写入：
1. 管理者长期展示偏好
2. 系统规则
3. 禁止项
4. 员工参与项目关系
5. 团队长期上下文
6. 项目长期背景
7. 仓库路径与业务模块映射
8. 可复用经验教训
9. 稳定事实

不得写入长期记忆：
1. 员工某天具体做了什么
2. 具体 commit / diff 内容
3. 临时会议细节
4. 一次性日报内容
5. 原始代码或完整 diff
6. 密钥、token、连接串
7. 对员工的负面人格评价
```

---

### 10.3 新增 DailySyncMemoryService

```python
class DailySyncMemoryService:
    def __init__(self, memory_module):
        self.memory = memory_module

    def remember_manager_preference(self, manager_id: str, content: str) -> None:
        ...

    def remember_employee_project_relation(self, employee_id: str, project_id: str) -> None:
        ...

    def remember_project_context(self, project_id: str, content: str) -> None:
        ...

    def remember_lesson(self, content: str, source: str) -> None:
        ...

    def search_report_context(self, team_id: str, project_id: str | None, query: str) -> str:
        ...
```

---

### 10.4 修改 Compressor 章节

原通用压缩章节可改为 DailySync 风格：

```text
### 管理者当前关注点
### 本次对话结论
### 已确认的团队事实
### 已确认的项目进展
### 风险 / 阻塞
### 管理者偏好变化
### 后续待跟进
### 不应遗忘的表达规则
```

---

## 11. Phase 划分建议

### Phase 0：概念收敛

完成：

- 明确 DailySync 不是知识库，而是记忆系统
- 明确员工工作公开边界
- 明确长期记忆只记录稳定上下文
- 明确 Gitea 第一版不 fork
- 明确系统规则优先级
- 明确日报 / 周报调度时间

---

### Phase 1：DailySync 最小闭环

实现：

- Gitea Adapter
- 员工身份映射
- 噪声过滤
- Diff Evidence Pack
- 员工每日工作清单
- 日报生成 JSON
- 周报生成 JSON
- 企业 IM 卡片推送
- 现有 memory_module 接入
- Policy 三个初始禁止项
- 基础审计

目标：

```text
工作日 21:00 自动生成并推送团队日报。
每周末 18:00 自动生成并推送团队周总结。
```

---

### Phase 2：管理者查询与记忆增强

实现：

- 管理者对话式查询
- DailySync MCP / DailySync Tools
- 管理者偏好记忆
- 项目上下文记忆
- 员工项目关系自动提炼
- 经验教训自动沉淀
- 卡片详情页
- 卡片导出图片

---

### Phase 3：多数据源扩展

实现：

- 任务系统接入：Jira / TAPD / 禅道
- 文档系统接入：飞书文档 / 语雀 / Confluence
- 行政系统接入：OA / 日历 / 邮箱
- 用户自助绑定数据源
- 不同岗位的工作事件适配器

---

### Phase 4：Gitea 深度增强

仅在必要时考虑：

- fork Gitea 增加 DailySync 专用 Evidence Pack 接口
- 增加 Gitea 页面内日报证据入口
- 增加 DailySync CLI
- 增强 Gitea MCP 只读工具

前提：

```text
只有当 API / Tea CLI / Gitea MCP / 本地 git 命令无法满足性能、权限或数据粒度要求时，才进入这一阶段。
```

---

## 12. 最重要的架构结论

修订后的 DailySync 架构结论如下：

1. **原方案底座保留**：Kernel、Runtime、Registry、Memory、Skill、Model、Policy 仍然是正确平台底座。
2. **新增 DailySync Domain Layer**：Gitea、身份映射、噪声过滤、Evidence Pack、日报、周报、卡片都属于领域层，不进入 Kernel。
3. **不把记忆系统叫知识库**：DailySync 使用现有 `memory_module` 作为智能体记忆系统。
4. **长期记忆不记每日工作细节**：只记管理者偏好、系统规则、员工项目关系、项目上下文、经验教训等稳定上下文。
5. **员工工作公开，不是隐私公开**：组织内可见的是工作摘要和经验，不是原始代码、完整 diff、密钥、私人信息和系统内部规则。
6. **Gitea 第一版不 fork**：优先复用 Gitea API、Tea CLI、Gitea MCP、本地 git 命令。
7. **身份映射和噪声过滤前置**：先确认“谁做的、哪些算、哪些不算”，再进入 AI 分析。
8. **Evidence Pack 是质量核心**：模型消费结构化证据，而不是完整 diff。
9. **日报不固定条数**：由 AI 根据信息密度动态生成。
10. **卡片由前端模板渲染**：AI 负责内容，前端负责样式，不用图片模型直接生成日报图。
11. **Policy 是硬约束**：系统规则和禁止项优先于管理者偏好和 prompt。
12. **第一版目标是稳定闭环**：Gitea → Evidence Pack → 记忆 → 日报 / 周报 → 卡片推送。

---

## 13. 下一步建议

正式开发前，建议补三份更具体的接口文档：

### 13.1 DailySync 核心接口契约文档

定义：

- GiteaAdapter
- IdentityMapper
- NoiseFilter
- EvidencePackBuilder
- ReportGenerator
- CardRenderer
- DailySyncMemoryService
- PolicyGuard
- IMAdapter

---

### 13.2 DailySync 任务时序文档

用时序图描述：

```text
Scheduler
  -> TaskManager
  -> GiteaAdapter
  -> IdentityMapper
  -> NoiseFilter
  -> EvidencePackBuilder
  -> MemoryService
  -> ReportGenerator
  -> PolicyGuard
  -> CardRenderer
  -> IMAdapter
  -> Audit
```

---

### 13.3 MemoryModule 改造文档

明确：

- 新 section 白名单
- 新长期记忆提炼 prompt
- 新压缩 prompt
- DailySyncMemoryService 封装
- source 命名规范
- org_visible / system_internal / raw_sensitive 边界

---

## 14. 当前版本建议执行清单

```text
[ ] 保留原 Agent Runtime Kernel 文档作为底座文档
[ ] 新增 DailySync Domain Layer 文档
[ ] 修改 Memory Service 描述为 Memory System
[ ] 扩展长期记忆 section
[ ] 改写 MemoryJudge prompt
[ ] 新增 DailySyncMemoryService
[ ] 定义 GiteaAdapter 接口
[ ] 定义 EvidencePack JSON schema
[ ] 定义 DailyReport JSON schema
[ ] 定义 WeeklyReport JSON schema
[ ] 定义三条初始禁止项
[ ] 定义工作日 21:00 日报任务
[ ] 定义每周末 18:00 周报任务
[ ] 定义企业 IM 卡片模板
[ ] 定义员工每日工作清单表单
```

---

## 15. 修订后的一句话定义

> DailySync 是一个本地部署的管理者辅助智能体，通过 Gitea 工作事件、员工补充清单和记忆系统，生成可信、低侵入、可追溯的日报与周报，并以管理者习惯适配的方式提供查询和风险提醒，同时避免原始代码暴露和员工监控化表达。
