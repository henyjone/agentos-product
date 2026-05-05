# AgentOS 组织记忆系统详细设计方案

版本：v0.1  
日期：2026-05-05  
负责人：HGZ  
状态：设计草案，可作为后续实现和接口对齐依据

---

## 1. 文档目标

本文档定义 AgentOS 的组织记忆系统设计。

本方案基于以下共识：

1. 旧的 `D:\pro\chatbot\src\memory_module` 是一个优秀的个人长会话记忆模块，但它的中心对象是 `session`，不适合作为 AgentOS 的组织级记忆主模型。
2. AgentOS 需要的是以项目、人员、仓库、事件、事实、关系、权限为中心的组织记忆系统。
3. 当前 `agent_engine` 只是骨架，可以直接替换，不应成为架构约束。
4. 当前真正有价值的功能主要在：
   - `src/commit_guide`
   - `src/repo_analyzer`
5. 新组织记忆系统应直接承接 `commit_guide` 和 `repo_analyzer` 的数据与能力，而不是在空的 `agent_engine` 骨架上打补丁。

本文档回答：

- AgentOS 的组织记忆系统应如何建模？
- `commit_guide` 和 `repo_analyzer` 如何接入组织记忆？
- 组织记忆如何支持项目总结、员工完成工作、详细工作日志、管理者日报和后续 Agent 调用？
- 什么交给推理模型，什么交给遵循命令的大模型，什么固化成代码脚本？
- MVP 阶段如何实现，后续如何对接 Dev1 后端数据库？

---

## 2. 总体结论

AgentOS 应新建一套组织记忆内核，建议模块名：

```text
org_memory
```

它不应直接复用旧 `memory_module` 作为主架构。

旧 `memory_module` 可作为参考和局部能力迁移来源，例如：

- 事件日志思想
- 中期 / 长期记忆分层思想
- 压缩前 durable flush 思想
- 异步任务幂等和恢复机制
- BM25 + 向量检索
- 审计事件记录

但组织记忆的核心模型必须重写。

核心差异：

| 维度 | 旧 memory_module | 新 org_memory |
|---|---|---|
| 中心对象 | 会话 session | 项目、人员、仓库、事件、事实、关系 |
| 主要场景 | 个人聊天长期记忆 | 公司组织运行记忆 |
| 事实粒度 | rule_key + content | entity + event + fact + source + scope |
| 权限边界 | 较弱，偏个人本地 | 必须内建 personal / team / org / restricted |
| 来源追溯 | source 字段较简单 | source_id 必须可追溯到 commit、文档、会议、任务等 |
| 检索方式 | 记忆条目检索 | 结构化过滤 + BM25 + 向量 + 关系扩展 |
| 视图 | MEMORY.md / daily md | 项目视图、人员视图、团队视图、日报视图 |

一句话：

> 旧模块是“个人聊天记忆系统”，新模块应是“组织事实与记忆系统”。

---

## 3. 与现有模块的关系

### 3.1 commit_guide 的定位

`commit_guide` 是员工端提交入口。

它当前已经具备：

- 读取 staged 文件列表
- 读取 staged diff
- 按文件优先级截断 diff，优先保留代码变更
- 调用 AI 生成 commit message
- 用户确认后执行 commit
- 多 remote 选择和推送重试

在组织记忆系统里，`commit_guide` 应成为“员工主动提交事件”的来源。

它能提供：

| 字段 | 来源 |
|---|---|
| repo | 当前 Git 仓库 |
| branch | 当前分支 |
| staged_files | 暂存文件 |
| diff_context | 分文件 diff 摘要 |
| commit_message | AI 生成或人工确认的提交说明 |
| commit_sha | 提交成功后的 sha |
| push_remote | 推送目标 |
| actor | 当前 Git 用户或系统用户 |
| created_at | 提交时间 |

未来建议：

```text
commit_guide
  -> 成功提交后生成 RawEvent(commit_guide_submit)
  -> 写入 org_memory 或调用 Backend Memory API
```

### 3.2 repo_analyzer 的定位

`repo_analyzer` 是管理端 Gitea 仓库扫描和代码证据采集器。

它当前已经具备：

- 扫描单仓库或所有可见仓库
- 拉取 commits / issues / PRs / branches
- 拉取 commit detail、changed files、patch
- 读取变更文件内容快照
- 读取根目录项目上下文文件：
  - `项目背景.md`
  - `项目进度.md`
  - `项目目的.md`
  - `README.md`
- 生成管理者简版日报
- 生成指定员工 / 项目 / 路径 / commit 范围的详细工作日志

在组织记忆系统里，`repo_analyzer` 应成为“组织代码与项目状态事件”的主要采集器。

它能提供：

| 数据 | 记忆用途 |
|---|---|
| commits | 员工完成工作、项目活动、代码变更事实 |
| commit_details | 代码证据、文件级实现判断 |
| issues | 项目待办、阻塞、风险 |
| PRs | 待评审、待合并、协作状态 |
| branches | 并行开发状态 |
| project_context | 项目背景、目的、当前阶段、模块状态 |
| daily report | 管理者可读视图 |
| detail worklog | 按需深度事实提炼 |

未来建议：

```text
repo_analyzer
  -> fetch Gitea data
  -> convert to RawEvent / Entity / Source
  -> use AI extractor to derive Fact
  -> write Facts and Relationships into org_memory
  -> report reads from org_memory + fresh scan
```

### 3.3 agent_engine 的定位调整

当前 `agent_engine` 可替换。

新的定位应是：

```text
agent_engine = 统一 Agent 编排层
org_memory = 组织记忆和上下文层
repo_analyzer = Gitea 数据采集和分析管道
commit_guide = 员工提交入口和提交事件来源
```

也就是说：

```text
用户问题 / 定时任务 / 页面入口
        |
        v
agent_engine
        |
        +-- skill_router
        +-- org_memory context_builder
        +-- model client
        +-- response builder
```

`agent_engine` 不直接保存记忆。

---

## 4. 核心设计原则

### 4.1 事件先行

系统先记录“发生了什么”，再让 AI 提炼“这意味着什么”。

例如：

```text
RawEvent:
  HGZ 在 HGZ/agentos-product 提交了 commit 95bea09

Fact:
  HGZ 完成了 repo_analyzer 渲染模块重构

Inference:
  repo_analyzer 的报告生成逻辑更容易维护
```

事件是事实来源，AI 结论是派生结果。

### 4.2 来源可追溯

每条事实必须能追溯来源。

来源可以是：

- commit
- diff
- changed file
- issue
- PR
- 项目文档
- 会议纪要
- 任务系统
- 人工录入
- AI 生成的报告

没有来源的内容不能进入高置信事实。

### 4.3 权限先过滤，再检索

检索不能先搜全量再让 AI 自己判断能不能用。

正确顺序：

```text
user + role + entry_point
  -> permission filter
  -> scope filter
  -> structured filter
  -> keyword/vector/graph retrieval
  -> context build
  -> model call
```

### 4.4 Markdown 是视图，不是唯一事实源

保留 Markdown，但定位要清楚：

| 类型 | 定位 |
|---|---|
| `项目背景.md` | 人工维护的项目背景事实源 |
| `项目进度.md` | 人工维护的项目进度事实源 |
| `项目目的.md` | 人工维护的项目目标事实源 |
| `README.md` | 仓库入口和说明 |
| `memory_views/*.md` | 由系统生成的人和 AI 可读视图 |

机器采集事件、AI 提炼事实、权限、审计、关系，不应只存 Markdown。

### 4.5 模型分工

AgentOS 中任务不应粗暴分为“代码做”和“AI 做”。

推荐三层分工：

| 类型 | 承担者 | 示例 |
|---|---|---|
| 决策任务 | 推理模型 | 风险判断、事实冲突合并、复杂总结、模式选择 |
| 确定性语言任务 | 遵循命令能力强的大模型 | 按 schema 抽取事实、整理工作日志、生成结构化 JSON |
| 固化操作 | 代码脚本 | 拉 Gitea、解析 diff、写数据库、权限过滤、渲染 Markdown、同步向量 |

---

## 5. 总体架构

```text
                    +---------------------+
                    |     commit_guide    |
                    | 员工提交入口 / diff  |
                    +----------+----------+
                               |
                               v
                    +---------------------+
                    |    RawEvent Ingest  |
                    +----------+----------+
                               |
+------------------+           |            +--------------------+
|  repo_analyzer   |-----------+------------|  project docs      |
| Gitea 扫描/证据   |                        | 背景/进度/目的/README |
+------------------+                        +--------------------+
                               |
                               v
              +-----------------------------------+
              |             org_memory            |
              |-----------------------------------|
              | Entity Registry                   |
              | Raw Event Ledger                  |
              | Source Store                      |
              | Fact Store                        |
              | Relationship Graph                |
              | Scope / Permission Filter         |
              | Retrieval / Context Builder       |
              | Markdown View Generator           |
              +----------------+------------------+
                               |
                               v
              +-----------------------------------+
              |            agent_engine           |
              |-----------------------------------|
              | Project + Person + Entry Router   |
              | Skill / Chain Runner              |
              | Model Client                      |
              | Response Builder                  |
              | Risk / Action Generator           |
              +----------------+------------------+
                               |
                               v
              +-----------------------------------+
              | Dev1 Backend / Dev3 Frontend      |
              | API / DB / Approval / UI / Audit  |
              +-----------------------------------+
```

---

## 6. 核心数据模型

### 6.1 Entity

Entity 表示组织里的稳定对象。

```json
{
  "id": "project:agentos-product",
  "type": "project",
  "name": "AgentOS",
  "aliases": ["agentos-product", "HGZ/agentos-product"],
  "owner_id": "person:HGZ",
  "status": "active",
  "scope": "team",
  "sensitivity": "internal",
  "metadata": {
    "repo_full_name": "HGZ/agentos-product"
  },
  "created_at": "2026-05-05T00:00:00+08:00",
  "updated_at": "2026-05-05T00:00:00+08:00"
}
```

Entity 类型：

| type | 示例 |
|---|---|
| `person` | HGZ、张瑞 |
| `team` | AI Agent Team |
| `project` | AgentOS |
| `repo` | HGZ/agentos-product |
| `module` | repo_analyzer、commit_guide |
| `commit` | 95bea09 |
| `pull_request` | PR #12 |
| `issue` | Issue #7 |
| `document` | 项目进度.md |
| `task` | 后端 API 框架 |
| `decision` | 采用 org_memory 新内核 |
| `skill` | management_brief_skill |

### 6.2 RawEvent

RawEvent 表示外部系统或用户行为产生的原始事件。

```json
{
  "id": "event:gitea_commit:HGZ/agentos-product:95bea09",
  "event_type": "gitea_commit",
  "actor_id": "person:HGZ",
  "project_id": "project:agentos-product",
  "repo_id": "repo:HGZ/agentos-product",
  "occurred_at": "2026-05-04T16:20:00+08:00",
  "source_id": "source:gitea_commit:95bea09",
  "scope": "team",
  "sensitivity": "internal",
  "payload": {
    "sha": "95bea09",
    "message": "refactor(repo-analyzer): 重构分析器，提取渲染模块并简化输出逻辑",
    "branch": "main",
    "files": ["src/repo_analyzer/analyzer.py", "src/repo_analyzer/rendering.py"],
    "additions": 120,
    "deletions": 80
  },
  "ingested_at": "2026-05-05T10:00:00+08:00"
}
```

事件类型第一版建议：

| event_type | 来源 |
|---|---|
| `commit_guide_submit` | 员工通过 commit_guide 成功提交 |
| `gitea_commit` | repo_analyzer 从 Gitea 拉取 commit |
| `gitea_pr` | repo_analyzer 从 Gitea 拉取 PR |
| `gitea_issue` | repo_analyzer 从 Gitea 拉取 issue |
| `project_doc_update` | 项目背景/进度/目的/README |
| `manager_daily_report` | 管理者日报生成结果 |
| `detail_worklog` | 详细扫描生成的工作日志 |
| `manual_note` | 人工补充 |
| `agent_decision` | Agent 形成的决策建议 |

### 6.3 Source

Source 是可展示、可引用、可审计的来源。

```json
{
  "id": "source:gitea_commit:95bea09",
  "title": "refactor(repo-analyzer): 重构分析器，提取渲染模块并简化输出逻辑",
  "url": "http://192.168.0.111:3000/HGZ/agentos-product/commit/95bea09",
  "source_type": "code",
  "system": "gitea",
  "sensitivity": "internal",
  "created_at": "2026-05-04T16:20:00+08:00",
  "metadata": {
    "repo": "HGZ/agentos-product",
    "sha": "95bea09"
  }
}
```

`source_type` 合法值：

```text
project | meeting | document | customer_event | task | code | manual | report | chat
```

### 6.4 Fact

Fact 是可复用的组织事实。

```json
{
  "id": "fact:work:HGZ:agentos-product:20260504:repo_analyzer_rendering",
  "fact_type": "employee_completed_work",
  "content": "HGZ 完成了 repo_analyzer 渲染逻辑重构，将渲染职责提取到独立模块。",
  "subject_entity_id": "person:HGZ",
  "object_entity_id": "project:agentos-product",
  "project_id": "project:agentos-product",
  "source_ids": ["source:gitea_commit:95bea09"],
  "confidence": "high",
  "scope": "team",
  "sensitivity": "internal",
  "valid_from": "2026-05-04",
  "valid_to": null,
  "created_by": "ai:repo_analyzer_detail",
  "created_at": "2026-05-05T10:00:00+08:00",
  "updated_at": "2026-05-05T10:00:00+08:00",
  "status": "active"
}
```

第一版 Fact 类型：

| fact_type | 含义 |
|---|---|
| `employee_completed_work` | 员工完成了某项工作 |
| `project_current_phase` | 项目当前阶段 |
| `project_module_status` | 项目模块状态 |
| `project_blocker` | 项目阻塞 |
| `project_risk` | 项目风险 |
| `project_next_step` | 项目下一步 |
| `code_change_summary` | 代码变更摘要 |
| `decision_record` | 决策记录 |
| `source_summary` | 来源摘要 |

`confidence` 合法值：

```text
high | medium | low
```

### 6.5 Relationship

Relationship 描述实体之间的关系。

```json
{
  "id": "rel:person:HGZ:works_on:project:agentos-product",
  "from_entity_id": "person:HGZ",
  "to_entity_id": "project:agentos-product",
  "relation_type": "works_on",
  "source_ids": ["source:gitea_commit:95bea09"],
  "confidence": "high",
  "scope": "team",
  "sensitivity": "internal",
  "created_at": "2026-05-05T10:00:00+08:00",
  "updated_at": "2026-05-05T10:00:00+08:00"
}
```

第一版关系类型：

| relation_type | 示例 |
|---|---|
| `works_on` | 人参与项目 |
| `owns` | 人负责项目或模块 |
| `belongs_to` | 仓库属于项目 |
| `touches_module` | commit 影响模块 |
| `blocks` | issue 阻塞项目 |
| `depends_on` | 项目依赖另一个项目 |
| `mentions` | 文档或事件提到某实体 |
| `generated_by` | fact 由某报告或模型生成 |

### 6.6 Scope 与 Sensitivity

`scope` 表示访问边界：

| scope | 含义 | 默认可见性 |
|---|---|---|
| `personal` | 个人记忆、私人讨论、个人偏好 | 本人 |
| `team` | 团队协作数据、项目上下文 | 团队成员和授权负责人 |
| `org` | 公司级公开事实、跨团队决策 | 按组织权限 |
| `restricted` | 人事、财务、法务、安全事件 | 默认不进入普通 Agent 上下文 |

`sensitivity` 表示敏感级别：

| sensitivity | 含义 |
|---|---|
| `public` | 可公开 |
| `internal` | 公司内部 |
| `private` | 私人 |
| `restricted` | 强隔离 |

规则：

1. `restricted` 默认不能进入普通日报和普通问答。
2. `personal` 不能自动提升为 `team` 或 `org`。
3. 私人共事内容只有用户确认后才能转为团队公开事实。
4. 凭据类内容不能进入明文记忆，只能保存 secret reference。

---

## 7. 项目 + 人员 => 技能的决策树

AgentOS 不采用 GBrain 那种“页面目录决策树”。

本项目应采用：

```text
项目 + 人员 + 入口 + 意图 + 权限 => skill / chain
```

### 7.1 SkillRoute 输入

```json
{
  "user_id": "person:HGZ",
  "role": "manager",
  "entry_point": "manager_daily",
  "message": "今天谁完成了什么工作？",
  "context_hint": {
    "project_id": "project:agentos-product",
    "person_id": null,
    "repo_id": null,
    "time_range": "last_1_day"
  },
  "requested_action": null
}
```

### 7.2 SkillRoute 输出

```json
{
  "skill_id": "management_brief_skill",
  "mode": "management",
  "retrieval_plan": {
    "project_ids": ["project:agentos-product"],
    "person_ids": [],
    "fact_types": ["employee_completed_work", "project_risk", "project_blocker"],
    "source_types": ["code", "document", "report"],
    "time_range": "last_1_day",
    "scope_allowed": ["team", "org"]
  },
  "requires_approval": false,
  "reason": "管理者日报入口，问题关注员工完成工作和项目状态。"
}
```

### 7.3 第一版路由规则

| 条件 | skill |
|---|---|
| `entry_point=manager_daily` | `management_brief_skill` |
| `entry_point=repo_detail_scan` | `repo_detail_worklog_skill` |
| `entry_point=project_status` 或存在 `project_id` | `project_status_skill` |
| `entry_point=personal_daily` 或存在 `person_id=user_id` | `personal_brief_skill` |
| 用户要求“陪我想” | `cowork_skill` |
| 用户问知识事实 | `knowledge_answer_skill` |
| 用户要求发消息/建任务/改状态 | `execution_skill` + approval |
| 用户要求访问权限/审计 | `governance_skill` |

---

## 8. 存储设计

### 8.1 MVP 存储策略

MVP 阶段建议实现两层适配：

```text
MemoryStore Protocol
  -> LocalSQLiteMemoryStore       本地开发 / Python 自测
  -> BackendMemoryStore           后续对接 Dev1 Java 后端 API
```

不建议只用 JSON/Markdown 作为主存储。

原因：

- 组织记忆需要结构化过滤。
- 权限和 scope 需要可靠查询。
- facts / entities / relationships 需要去重和更新。
- 管理者日报需要按人、项目、时间聚合。

Markdown 仍然保留，但作为视图：

```text
memory_views/
  projects/
    project-agentos-product.md
  people/
    person-HGZ.md
  daily/
    2026-05-05.md
```

### 8.2 SQLite 表草案

```sql
CREATE TABLE entities (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  name TEXT NOT NULL,
  aliases_json TEXT NOT NULL DEFAULT '[]',
  owner_id TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  scope TEXT NOT NULL,
  sensitivity TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE sources (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  url TEXT,
  source_type TEXT NOT NULL,
  system TEXT NOT NULL,
  sensitivity TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE TABLE raw_events (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  actor_id TEXT,
  project_id TEXT,
  repo_id TEXT,
  source_id TEXT,
  occurred_at TEXT NOT NULL,
  ingested_at TEXT NOT NULL,
  scope TEXT NOT NULL,
  sensitivity TEXT NOT NULL,
  payload_json TEXT NOT NULL
);

CREATE TABLE facts (
  id TEXT PRIMARY KEY,
  fact_type TEXT NOT NULL,
  content TEXT NOT NULL,
  subject_entity_id TEXT,
  object_entity_id TEXT,
  project_id TEXT,
  source_ids_json TEXT NOT NULL DEFAULT '[]',
  confidence TEXT NOT NULL,
  scope TEXT NOT NULL,
  sensitivity TEXT NOT NULL,
  valid_from TEXT,
  valid_to TEXT,
  created_by TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE relationships (
  id TEXT PRIMARY KEY,
  from_entity_id TEXT NOT NULL,
  to_entity_id TEXT NOT NULL,
  relation_type TEXT NOT NULL,
  source_ids_json TEXT NOT NULL DEFAULT '[]',
  confidence TEXT NOT NULL,
  scope TEXT NOT NULL,
  sensitivity TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE memory_audit (
  id TEXT PRIMARY KEY,
  actor_id TEXT,
  action TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  reason TEXT,
  created_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);
```

### 8.3 后端正式存储

正式环境应由 Dev1 后端承接：

- 数据库表结构
- 权限判断
- 审计日志
- API 鉴权
- 版本管理

Python 侧只依赖 `MemoryStore` / `MemoryClient` 协议。

---

## 9. Python 模块结构

建议新增：

```text
src/
  org_memory/
    __init__.py
    domain.py
    ids.py
    scope.py
    time_utils.py

    store/
      __init__.py
      interface.py
      local_sqlite.py
      backend.py

    ingest/
      __init__.py
      commit_guide.py
      gitea.py
      project_docs.py

    extraction/
      __init__.py
      fact_extractor.py
      relation_extractor.py
      prompts.py

    retrieval/
      __init__.py
      hybrid.py
      context_builder.py

    routing/
      __init__.py
      skill_router.py
      route_rules.py

    views/
      __init__.py
      markdown_view.py

    governance/
      __init__.py
      policy.py
      audit.py

    pipelines/
      __init__.py
      repo_activity_pipeline.py
      work_summary_pipeline.py
      detail_worklog_pipeline.py

tests/
  org_memory_tests/
    test_domain.py
    test_scope.py
    test_local_sqlite_store.py
    test_gitea_ingest.py
    test_commit_guide_ingest.py
    test_project_docs_ingest.py
    test_skill_router.py
    test_context_builder.py
```

### 9.1 domain.py

定义核心数据类：

```python
Entity
Source
RawEvent
Fact
Relationship
MemoryQuery
MemoryContext
SkillRoute
IngestResult
```

### 9.2 store/interface.py

定义存储协议：

```python
class MemoryStore(Protocol):
    def upsert_entity(self, entity: Entity) -> None: ...
    def upsert_source(self, source: Source) -> None: ...
    def append_event(self, event: RawEvent) -> None: ...
    def upsert_fact(self, fact: Fact) -> None: ...
    def upsert_relationship(self, relationship: Relationship) -> None: ...
    def search_facts(self, query: MemoryQuery) -> list[Fact]: ...
    def list_events(self, query: MemoryQuery) -> list[RawEvent]: ...
    def audit(self, action: str, target_type: str, target_id: str, actor_id: str, reason: str) -> None: ...
```

### 9.3 ingest/gitea.py

把 `repo_analyzer` 的数据转成组织记忆事件。

输入：

```python
RepositoryActivity
```

输出：

```python
IngestResult(
    entities=[...],
    sources=[...],
    events=[...],
    relationships=[...]
)
```

### 9.4 ingest/commit_guide.py

把本地提交结果转成组织记忆事件。

输入：

```python
repo_path
branch
staged_files
diff_context
commit_message
commit_sha
push_remote
```

输出：

```python
RawEvent(event_type="commit_guide_submit")
Source(source_type="code")
Fact(fact_type="code_change_summary")
```

### 9.5 extraction/fact_extractor.py

负责从事件和代码证据中提炼事实。

第一版可以用大模型输出 JSON：

```json
{
  "facts": [
    {
      "fact_type": "employee_completed_work",
      "content": "HGZ 完成了 repo_analyzer 的详细扫描日志能力。",
      "subject_entity_id": "person:HGZ",
      "object_entity_id": "project:agentos-product",
      "source_ids": ["source:gitea_commit:32b8919"],
      "confidence": "high",
      "scope": "team",
      "sensitivity": "internal"
    }
  ],
  "relationships": []
}
```

要求：

- AI 不允许生成没有 source_id 的 high confidence fact。
- 若只有 commit message，无 diff 证据，最高只能是 medium。
- 若有 patch 或文件快照支持，可以是 high。
- 无法判断时输出 `confidence=low` 或不输出 fact。

### 9.6 retrieval/context_builder.py

负责给 Agent 组装上下文。

输入：

```json
{
  "user_id": "person:HGZ",
  "entry_point": "manager_daily",
  "project_ids": ["project:agentos-product"],
  "person_ids": [],
  "fact_types": ["employee_completed_work", "project_risk"],
  "time_range": "last_1_day",
  "max_items": 20
}
```

输出：

```json
{
  "facts": [],
  "sources": [],
  "relationships": [],
  "uncertainty": {
    "level": "low",
    "reason": ""
  }
}
```

---

## 10. 与 commit_guide 的集成设计

### 10.1 当前阶段

当前 `commit_guide` 仍然可以独立运行。

```powershell
python -m commit_guide.main --push
```

它负责：

1. 读取 staged diff。
2. 生成 commit message。
3. 用户确认。
4. 执行 commit / push。

### 10.2 下一阶段增强

新增可选参数：

```powershell
python -m commit_guide.main --push --write-memory
```

执行成功后写入组织记忆：

```text
commit-guide commit success
  -> CommitGuideIngestor
  -> RawEvent(commit_guide_submit)
  -> Source(code)
  -> Fact(code_change_summary)
  -> Relationship(person works_on project)
```

### 10.3 为什么 commit_guide 重要

`commit_guide` 能解决一个现实问题：

Gitea 后台扫描只能看到 commit 结果，而员工端提交工具能看到更完整的提交意图和 staged diff。

所以它可以提供更早、更清晰的员工工作信号。

---

## 11. 与 repo_analyzer 的集成设计

### 11.1 当前阶段

当前 `repo_analyzer` 的命令：

```powershell
python -m repo_analyzer.main --all-repos --days 1 --output reports\gitea-daily.md
```

详细扫描：

```powershell
python -m repo_analyzer.main --detail --repo-url "http://192.168.0.111:3000/HGZ/agentos-product" --days 1 --output reports\detail-agentos-product.md
```

### 11.2 下一阶段增强

新增可选参数：

```powershell
python -m repo_analyzer.main --all-repos --days 1 --write-memory
```

流程：

```text
fetch Gitea data
  -> build RepositoryActivity
  -> GiteaIngestor converts events/sources/entities
  -> FactExtractor extracts work/project facts
  -> MemoryStore persists
  -> report reads facts and fresh scan evidence
```

### 11.3 管理者日报的数据来源

未来日报不应只读即时扫描结果，而应读：

```text
fresh Gitea scan
+ org_memory facts
+ project context docs
+ previous reports
= manager daily brief
```

默认简版日报仍保持：

```text
谁完成了什么工作
```

详细分析按需触发：

```text
指定员工 / 项目 / 时间 / 路径 / commit
  -> 读取 diff + 文件内容 + 项目上下文
  -> 生成详细工作日志
  -> 可选写入 org_memory
```

### 11.4 当前代码证据能力是否已存在

已存在。

`repo_analyzer` 当前已经读取：

- commit detail
- changed files
- patch excerpts
- file content snapshots
- project context docs

后续要做的是把这些证据从“报告上下文”升级为“组织记忆来源”。

---

## 12. agent_engine 重建建议

当前 `agent_engine` 可以替换。

建议未来结构：

```text
src/
  agent_engine/
    __init__.py
    schemas.py
    orchestrator.py
    model.py
    response_builder.py
    risk.py
    actions.py
    chains/
      management_brief.py
      project_status.py
      personal_brief.py
      knowledge_answer.py
      cowork.py
      repo_detail_worklog.py
```

`agent_engine` 不内置复杂记忆逻辑，只调用：

```python
org_memory.routing.skill_router
org_memory.retrieval.context_builder
org_memory.store.interface.MemoryStore
```

核心调用流：

```text
AgentRequest
  -> SkillRouter
  -> MemoryContextBuilder
  -> Chain
  -> ModelClient
  -> ResponseBuilder
  -> RiskClassifier / ActionGenerator
  -> AgentResponse
```

---

## 13. 典型工作流

### 13.1 员工提交代码

```text
员工运行 commit_guide
  -> AI 生成 commit message
  -> 员工确认
  -> git commit
  -> git push
  -> org_memory 写入 commit_guide_submit event
```

生成：

- RawEvent
- Source
- Entity commit
- Relationship person works_on project
- Fact code_change_summary

### 13.2 管理者日报

```text
repo_analyzer --all-repos
  -> 扫描 Gitea
  -> 写入 org_memory
  -> 查询最近 1 天 employee_completed_work facts
  -> 生成简版日报
```

输出：

```text
HGZ
- 完成工作:
1. ...
2. ...
```

### 13.3 管理者要求详细查看

```text
manager asks detail
  -> SkillRouter: repo_detail_worklog_skill
  -> ContextBuilder: project + person + commit + code evidence
  -> DetailWorklogChain
  -> 生成详细工作日志
  -> 可选写入 detail_worklog event / facts
```

### 13.4 项目状态问答

```text
用户问：agentos-product 当前卡在哪里？
  -> project_status_skill
  -> 查询 project_blocker / project_risk / project_module_status
  -> 引用 项目进度.md + issue + PR + commit
  -> 输出事实 / 推断 / 建议
```

### 13.5 私人共事转公开事实

```text
员工在 cowork 模式讨论
  -> 默认 scope=personal
  -> 不进入 team/org
  -> 员工点击“生成公开版本”
  -> Agent 生成 memo/action
  -> 员工确认
  -> 写入 team scope fact
```

---

## 14. 权限和安全

### 14.1 明文凭据禁止进入记忆

禁止写入：

- 密码
- token
- API key
- cookie
- 私钥

应写入：

```text
credential_ref: vault://gitea/admin
```

不写真实值。

### 14.2 访问规则

第一版最小策略：

| 用户 | 可访问 |
|---|---|
| 员工本人 | personal + 授权 team/org |
| 团队负责人 | team + org + 聚合后的项目事实 |
| 管理者 | org + 授权 team + 管理聚合事实 |
| Admin/Security | audit + policy + break-glass |

### 14.3 审计事件

以下操作必须写审计：

- 写入 fact
- 删除 fact
- 修改 scope
- 访问 restricted 记忆
- 导出报告
- 生成高风险 action
- 人工覆盖 AI 提炼结果

---

## 15. AI 提炼规则

### 15.1 工作完成事实

输入：

- commit message
- changed files
- patch excerpt
- file content snapshot
- project docs

输出：

```json
{
  "fact_type": "employee_completed_work",
  "content": "...",
  "subject_entity_id": "person:HGZ",
  "object_entity_id": "project:agentos-product",
  "source_ids": ["..."],
  "confidence": "high|medium|low"
}
```

规则：

| 证据 | 最高 confidence |
|---|---|
| commit message only | medium |
| commit message + changed files | medium |
| patch excerpt / file snapshot 支持 | high |
| 项目文档中的计划但无 commit | low，不可写成完成 |

### 15.2 项目状态事实

项目状态来自：

- `项目进度.md`
- issues
- PRs
- recent commits
- detailed worklog

项目文档是项目状态的重要来源，但不是近期完成工作的来源。

### 15.3 风险事实

风险必须包含：

```json
{
  "risk": "...",
  "basis": "...",
  "severity": "high|medium|low",
  "source_ids": []
}
```

没有依据的风险不入库。

---

## 16. Markdown 视图设计

### 16.1 项目视图

路径：

```text
memory_views/projects/project-agentos-product.md
```

内容：

```markdown
# AgentOS 项目记忆视图

## 当前阶段

## 模块状态

## 最近完成工作

## 风险和阻塞

## 下一步

## 关键来源
```

### 16.2 人员视图

路径：

```text
memory_views/people/person-HGZ.md
```

内容：

```markdown
# HGZ 工作记忆视图

## 最近完成工作

## 参与项目

## 常见负责模块

## 待确认事项
```

### 16.3 每日视图

路径：

```text
memory_views/daily/2026-05-05.md
```

内容：

```markdown
# 2026-05-05 组织记忆日报

## 员工完成工作

## 项目状态变化

## 新增风险

## 需要确认的事实
```

---

## 17. 与 Dev1 / Dev3 / Dev4 的接口

### 17.1 需要 Dev1 对齐

| 内容 | 说明 |
|---|---|
| 数据库表结构 | entities / events / facts / relationships / sources / audit |
| Memory API | 读写事实、来源、实体、关系 |
| 权限 API | 根据 user/role/scope/sensitivity 过滤 |
| 审计 API | 记录访问、写入、导出、删除 |
| Approval API | 高风险 action 确认 |

### 17.2 需要 Dev3 对齐

| 内容 | 说明 |
|---|---|
| Source 展示 | facts 引用 sources |
| Fact/Inference/Suggestion 展示 | 结构化渲染 |
| 详情入口 | 从简版日报进入详细扫描 |
| 记忆视图页面 | 项目视图、人员视图、每日视图 |
| 确认按钮 | 私人内容转团队内容、AI fact 入库确认 |

### 17.3 需要 Dev4 对齐

| 内容 | 说明 |
|---|---|
| 数据源接入 | Gitea、任务系统、文档、会议 |
| Source 格式 | source_id / title / url / type / sensitivity |
| Context Retrieval | 按项目、人员、时间、scope 过滤 |
| Knowledge Index | 文档、会议、任务、代码证据索引 |

---

## 18. 分阶段落地计划

### Phase 1：本地组织记忆内核

目标：

- 新建 `src/org_memory`
- 完成 domain model
- 完成 local SQLite store
- 完成 project docs ingest
- 完成 Gitea activity ingest
- 完成基础 Markdown view

验收：

- 能把 `repo_analyzer` 的 `RepositoryActivity` 写入 org_memory。
- 能从 org_memory 查询某项目最近完成工作。
- 能生成项目视图和人员视图。

### Phase 2：接入 repo_analyzer

目标：

- `repo_analyzer --write-memory`
- 管理者日报可以读取 org_memory facts
- 详细扫描结果可选入库

验收：

- 再运行一次日报时，系统知道之前的总结和事实。
- 可人工删除错误 fact，避免污染后续分析。

### Phase 3：接入 commit_guide

目标：

- `commit_guide --write-memory`
- 提交成功后写入组织记忆
- 将本地 diff 意图与 Gitea commit 结果关联

验收：

- 一个 commit 能从员工端提交记录追溯到 Gitea commit。
- 管理者日报能利用 commit_guide 提供的提交意图。

### Phase 4：重建 agent_engine

目标：

- `agent_engine` 使用 org_memory 作为上下文层
- 实现 skill_router
- 实现 management_brief / project_status / repo_detail_worklog

验收：

- 用户可以按项目、人员、时间询问。
- Agent 输出带 source。
- 私人和团队 scope 不混用。

### Phase 5：对接 Dev1 后端

目标：

- BackendMemoryStore
- 权限 API
- 审计 API
- Approval API

验收：

- Python 不直接依赖本地 SQLite。
- 正式数据由后端统一管理。

---

## 19. 第一阶段开发顺序

1. 新建 `src/org_memory` 包和 `tests/org_memory_tests`。
2. 定义 `Entity`、`Source`、`RawEvent`、`Fact`、`Relationship`、`MemoryQuery`。
3. 实现 `MemoryStore` 协议。
4. 实现 `LocalSQLiteMemoryStore`。
5. 实现 `ProjectDocsIngestor`，读取项目根目录上下文文件。
6. 实现 `GiteaActivityIngestor`，接收 `RepositoryActivity`。
7. 实现基础 `FactExtractor`，先支持规则提炼，再接 AI 提炼。
8. 实现 `ContextBuilder`，按 project/person/time/scope 查询事实。
9. 实现 `MarkdownViewGenerator`，生成项目和人员视图。
10. 给 `repo_analyzer` 增加 `--write-memory` 参数。
11. 编写测试覆盖 ingest、store、query、view。
12. 再考虑 `commit_guide --write-memory`。

---

## 20. 验收标准

MVP 组织记忆系统完成标准：

- 能保存 Gitea commit / PR / issue / project docs 事件。
- 能把 commit 和人员、项目、仓库关联起来。
- 能保存 AI 提炼的员工完成工作 fact。
- 每个 fact 都有 source_ids。
- 能按项目、人员、时间查询 facts。
- 能区分 personal / team / org / restricted。
- 能生成项目 Markdown 视图和人员 Markdown 视图。
- repo_analyzer 能选择性写入 org_memory。
- 管理者日报能使用 org_memory 的历史事实。
- 错误 fact 可以删除或标记失效。
- 所有写入和删除都有 audit。

---

## 21. 关键风险

| 风险 | 影响 | 应对 |
|---|---|---|
| AI 提炼错误事实 | 污染组织记忆 | source/confidence/status/audit + 人工删除 |
| 权限设计太晚 | 后续返工大 | 第一版就内建 scope/sensitivity |
| 把 Markdown 当唯一事实源 | 查询和权限困难 | SQLite/后端为主，Markdown 为视图 |
| 过早做复杂图谱 | 拖慢 MVP | 第一版 relationships 只做基础关系 |
| 管理者日报变复杂 | 老板不爱看 | 默认只输出“谁完成了什么” |
| commit message 不规范 | 总结质量下降 | commit_guide 规范入口 + diff 证据补强 |

---

## 22. 设计决策记录

### ADR-001：新建 org_memory，而不是扩充旧 memory_module

决策：

新建组织记忆系统。

理由：

- 旧模块中心对象是 session。
- AgentOS 中心对象是 project/person/event/fact。
- 继续扩充会导致模型扭曲。

代价：

- 需要重新实现部分存储和检索接口。

收益：

- 长期架构更清晰。
- 更容易对接后端、权限和审计。

### ADR-002：Markdown 作为视图和人工项目上下文，不作为唯一事实源

决策：

项目文档是人工事实源；系统生成的 Markdown 是视图；结构化事件和事实存数据库。

理由：

- Markdown 适合人读和 AI 读。
- 数据库适合权限、查询、聚合、审计。

### ADR-003：路由采用项目 + 人员 => 技能

决策：

不采用页面目录式 resolver，采用项目、人员、入口、意图、权限共同决定 skill。

理由：

AgentOS 的核心问题是组织工作流，不是个人知识库页面归档。

---

## 23. 总结

AgentOS 的组织记忆系统应围绕：

```text
Entity + RawEvent + Source + Fact + Relationship + Scope
```

来设计。

当前最重要的不是继续扩充旧 `memory_module`，而是把 `commit_guide` 和 `repo_analyzer` 产生的真实工作信号沉淀为可追溯、可权限过滤、可检索、可被 Agent 调用的组织事实。

最终目标：

```text
员工提交代码
  -> 系统读取代码证据
  -> 形成可追溯工作事实
  -> 管理者看到简洁日报
  -> 需要时可深挖详细证据
  -> Agent 后续能基于这些事实回答项目和人员问题
```

这才是 AgentOS 作为公司 AI 操作系统的组织记忆基础。
