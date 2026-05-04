# Gitea AI 分析系统 - 详细设计文档

版本：v1.0
日期：2026-05-02
负责人：HGZ

---

## 1. 文档概述

### 1.1 文档目的

本文档是 Gitea AI 分析系统的详细设计文档，在统筹规划文档（v0.1）的基础上，对系统架构、模块设计、数据流、接口规范、安全策略、部署方案、测试策略等进行全面细化。

### 1.2 适用范围

本文档面向系统架构师、后端开发工程师、AI 工程师、测试工程师及项目管理者。

### 1.3 术语定义

| 术语 | 定义 |
|---|---|
| commit-guide | 员工端提交引导程序，运行于开发者本地环境 |
| repo-analyzer | 管理者端仓库分析程序，运行于管理者本地或服务器 |
| commit type | 标准化提交类型词汇（feat / fix / refactor / docs / test / chore / perf / revert） |
| config.json | 项目根目录下的统一 AI 模型配置文件 |
| Gitea API | Gitea 代码托管平台提供的 RESTful API 接口 |
| openai-compatible | 兼容 OpenAI Chat Completions 接口规范的 API 格式 |

---

## 2. 系统架构

### 2.1 架构概览

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Gitea AI 分析系统                              │
│                                                                      │
│  ┌──────────────────────┐          ┌──────────────────────────────┐  │
│  │    commit-guide       │          │      repo-analyzer            │  │
│  │    (员工端)            │          │      (管理者端)                │  │
│  │                       │          │                               │  │
│  │  ┌─────────────────┐  │          │  ┌──────────────────────────┐ │  │
│  │  │ main.py          │  │          │  │ main.py                  │ │  │
│  │  │ (交互主流程)      │  │          │  │ (入口/参数解析)           │ │  │
│  │  └────────┬────────┘  │          │  └───────────┬──────────────┘ │  │
│  │           │            │          │              │                │  │
│  │  ┌────────┴────────┐  │          │  ┌───────────┴──────────────┐ │  │
│  │  │ types.py         │  │          │  │ gitea_client.py          │ │  │
│  │  │ (词汇表)          │  │          │  │ (Gitea API 封装)         │ │  │
│  │  └────────┬────────┘  │          │  └───────────┬──────────────┘ │  │
│  │           │            │          │              │                │  │
│  │  ┌────────┴────────┐  │          │  ┌───────────┴──────────────┐ │  │
│  │  │ git_utils.py     │  │          │  │ data_builder.py          │ │  │
│  │  │ (Git 操作)        │  │          │  │ (数据组装)               │ │  │
│  │  └────────┬────────┘  │          │  └───────────┬──────────────┘ │  │
│  │           │            │          │              │                │  │
│  │  ┌────────┴────────┐  │          │  ┌───────────┴──────────────┐ │  │
│  │  │ ai_assist.py     │  │          │  │ analyzer.py              │ │  │
│  │  │ (AI 润色)         │  │          │  │ (AI 分析)                │ │  │
│  │  └────────┬────────┘  │          │  └───────────┬──────────────┘ │  │
│  │           │            │          │              │                │  │
│  │  ┌────────┴────────┐  │          │  ┌───────────┴──────────────┐ │  │
│  │  │ config_loader.py │  │          │  │ output.py                │ │  │
│  │  │ (配置读取)        │  │          │  │ (格式化输出)             │ │  │
│  │  └─────────────────┘  │          │  └──────────────────────────┘ │  │
│  └───────────────────────┘          │                               │  │
│                                      │  ┌──────────────────────────┐ │  │
│                                      │  │ config_loader.py         │ │  │
│                                      │  │ (配置读取)               │ │  │
│                                      │  └──────────────────────────┘ │  │
│                                      └──────────────────────────────┘  │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                    共享基础设施                                   │ │
│  │  ┌──────────────────┐  ┌──────────────────┐                     │ │
│  │  │ config.json       │  │ GITEA_TOKEN (env) │                    │ │
│  │  │ (AI 模型配置)      │  │ (Gitea 认证)      │                    │ │
│  │  └──────────────────┘  └──────────────────┘                     │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 系统分层

```
┌──────────────────────────────────────────────┐
│              表现层 (Presentation)             │
│  commit-guide: 终端交互界面 (CLI)              │
│  repo-analyzer: 终端输出 / Markdown 文件       │
├──────────────────────────────────────────────┤
│              业务逻辑层 (Business Logic)        │
│  commit-guide: 交互引导 / commit 拼装          │
│  repo-analyzer: 数据拉取编排 / AI 分析编排     │
├──────────────────────────────────────────────┤
│              服务层 (Service)                  │
│  AI 调用服务 / Git 操作服务 / Gitea API 服务   │
├──────────────────────────────────────────────┤
│              基础设施层 (Infrastructure)        │
│  config.json / 环境变量 / 文件系统 / 网络      │
└──────────────────────────────────────────────┘
```

### 2.3 两个程序的职责边界

```
commit-guide（员工端）              repo-analyzer（管理者端）
─────────────────────────          ─────────────────────────
✓ 检测 Git 仓库状态                 ✓ 调用 Gitea API
✓ 交互式引导填写 commit             ✓ 拉取 commits/issues/PRs/branches
✓ 拼装标准化 commit message         ✓ 按 commit type 分类统计
✓ 执行 git commit                   ✓ 调用 AI 生成摘要
✓ AI 辅助润色（可选）                ✓ 识别风险信号
✗ 不执行 git add                    ✓ 输出项目状态报告
✗ 不执行 git push                   ✗ 不修改 Gitea 仓库内容
✗ 不连接 Gitea API                  ✗ 不执行 git 操作
✗ 不分析仓库历史                    ✗ 不引导员工提交
```

---

## 3. 数据流设计

### 3.1 整体数据流

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ 开发者     │    │ Git 本地  │    │  Gitea   │    │ 管理者    │
│ 本地环境   │    │ 仓库      │    │  服务器   │    │ 本地/服务器│
└─────┬─────┘    └─────┬─────┘    └─────┬─────┘    └─────┬─────┘
      │                │               │                │
      │ ① 启动         │               │                │
      │ commit-guide   │               │                │
      │───────────────>│               │                │
      │                │               │                │
      │ ② 检测仓库状态  │               │                │
      │<───────────────│               │                │
      │                │               │                │
      │ ③ 交互引导      │               │                │
      │ (选择type/scope │               │                │
      │  填写描述)      │               │                │
      │                │               │                │
      │ ④ AI润色(可选)  │               │                │
      │                │               │                │
      │ ⑤ 确认并提交    │               │                │
      │───────────────>│               │                │
      │                │               │                │
      │ ⑥ git commit   │               │                │
      │                │               │                │
      │ ⑦ git push     │               │                │
      │──────────────────────────────>│                │
      │                │               │                │
      │                │               │ ⑧ 启动         │
      │                │               │ repo-analyzer  │
      │                │               │<───────────────│
      │                │               │                │
      │                │               │ ⑨ 拉取数据      │
      │                │               │ (commits/      │
      │                │               │  issues/PRs/   │
      │                │               │  branches)     │
      │                │               │───────────────>│
      │                │               │                │
      │                │               │ ⑩ AI 分析      │
      │                │               │───────────────>│
      │                │               │                │
      │                │               │ ⑪ 输出报告      │
      │                │               │───────────────>│
```

### 3.2 commit-guide 内部数据流

```
用户输入
  │
  ▼
┌─────────────┐
│ main.py      │ ◄── 流程控制器
│ 交互主循环    │
└──────┬──────┘
       │
       ├──► git_utils.py.get_status()
       │    返回: {staged: [...], unstaged: [...], untracked: [...]}
       │
       ├──► types.py.get_commit_types()
       │    返回: [{type: "feat", desc: "新功能"}, ...]
       │
       ├──► 用户选择 type → 用户输入 scope → 用户输入描述
       │
       ├──► ai_assist.py.polish(type, scope, description) [可选]
       │    返回: {suggestion: "...", accepted: bool}
       │
       └──► git_utils.py.commit(formatted_message)
            返回: {success: bool, sha: "..."}
```

### 3.3 repo-analyzer 内部数据流

```
CLI 参数 (--repo-url, --days, --branch)
  │
  ▼
┌─────────────┐
│ main.py      │ ◄── 参数解析 + 流程编排
└──────┬──────┘
       │
       ├──► gitea_client.py.fetch_commits(repo, branch, since)
       │    返回: [{sha, message, author, date}, ...]
       │
       ├──► gitea_client.py.fetch_issues(repo, state="open")
       │    返回: [{id, title, state, created_at, labels}, ...]
       │
       ├──► gitea_client.py.fetch_pull_requests(repo, state="open")
       │    返回: [{id, title, state, created_at, author}, ...]
       │
       ├──► gitea_client.py.fetch_branches(repo)
       │    返回: [{name, last_commit}, ...]
       │
       ├──► data_builder.py.build_context(commits, issues, prs, branches)
       │    返回: str (结构化上下文文本)
       │
       ├──► analyzer.py.analyze(context)
       │    返回: {summary, facts, inferences, risks, suggestions}
       │
       └──► output.py.render(result, format="terminal"|"markdown")
            返回: str (格式化后的报告)
```

---

## 4. 配置管理详细设计

### 4.1 config.json 结构规范

实际文件结构如下（`config格式.json` 为脱敏后的格式参考）：

```json
{
    "models": {
        "chat_glm": {
            "模型描述": "对话模型glm",
            "api_style": "openai-compatible",
            "api_key": "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            "api_base": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
            "model": "GLM-4.7-Flash"
        },
        "chat_qwen": {
            "模型描述": "对话模型qwen",
            "api_style": "openai-compatible",
            "api_key": "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            "api_base": "https://api.siliconflow.cn/v1/chat/completions",
            "model": "Qwen/Qwen3-VL-32B-Thinking"
        },
        "embedding": {
            "模型描述": "嵌入模型",
            "api_style": "openai-compatible",
            "api_key": "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            "api_base": "https://api.siliconflow.cn/v1/chat/completions",
            "model": "baai/bge-m3"
        }
    },
    "default_chat_model": "chat_glm"
}
```

### 4.2 配置字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `models` | object | 是 | 模型配置集合，key 为模型别名 |
| `models.{alias}.模型描述` | string | 否 | 中文描述，便于人工识别 |
| `models.{alias}.api_style` | string | 是 | API 风格标识，当前均为 `"openai-compatible"` |
| `models.{alias}.api_base` | string | 是 | API 端点完整 URL（已含 `/chat/completions` 等路径后缀），直接用于 HTTP 请求 |
| `models.{alias}.api_key` | string | 是 | API 认证密钥 |
| `models.{alias}.model` | string | 是 | 模型标识符，传给 API 的 model 参数 |
| `default_chat_model` | string | 是 | 默认使用的模型别名，必须在 models 中存在 |

> **注意**：`api_base` 已包含完整路径（如 `/v1/chat/completions`），调用时直接使用该 URL，**不需要再拼接路径后缀**。`max_tokens`、`temperature` 等参数不在配置中预设，由各调用方按需传入。</ezparameter>


### 4.3 配置加载流程

```
config_loader.py
  │
  ├── load_config()
  │     ├── 1. 确定 config.json 路径
  │     │     路径 = 项目根目录 / "config.json"
  │     │     项目根目录 = 向上查找包含 config.json 的目录
  │     │     或通过环境变量 PROJECT_ROOT 指定
  │     │
  │     ├── 2. 读取并解析 JSON
  │     │     异常: FileNotFoundError → 提示用户创建 config.json
  │     │     异常: JSONDecodeError → 提示用户检查 JSON 格式
  │     │
  │     ├── 3. 校验必填字段
  │     │     models 必须存在且非空
  │     │     default_chat_model 必须在 models 中存在
  │     │     default_chat_model 对应的模型必须有 api_base, api_key, model
  │     │
  │     └── 4. 返回配置字典
  │
  ├── get_default_model_config()
  │     └── 返回 default_chat_model 对应的模型配置
  │         返回字段: {api_base, api_key, model, api_style}
  │
  └── get_model_config(alias: str)
        └── 返回指定别名的模型配置，不存在则抛 KeyError

> **MVP 阶段**：commit-guide 和 repo-analyzer 各自独立复制一份 `config_loader.py`，不抽取共享模块。后续两个程序稳定后再考虑抽取到公共目录。
```

### 4.4 环境变量规范

| 变量名 | 用途 | 必填 | 使用方 |
|---|---|---|---|
| `GITEA_TOKEN` | Gitea API 访问令牌 | repo-analyzer 必填 | repo-analyzer |
| `PROJECT_ROOT` | 项目根目录路径（可选覆盖自动检测） | 否 | 两个程序 |

---

## 5. 安全设计

### 5.1 认证与密钥管理

```
安全原则:
  ✓ API Key 仅存储在 config.json 中，不硬编码
  ✓ config.json 加入 .gitignore，不提交到版本控制
  ✓ Gitea Token 仅通过环境变量传入，不写入任何文件
  ✓ 日志中不输出 API Key 和 Token
  ✓ 错误信息中不暴露密钥内容
```

### 5.2 权限最小化

```
commit-guide:
  - 仅需本地 Git 仓库读写权限
  - AI 调用仅用于润色建议，不自动执行

repo-analyzer:
  - Gitea Token 仅需只读权限（read:repository, read:issue, read:user）
  - 不对 Gitea 仓库执行任何写操作
  - AI 调用仅用于分析，不自动触发任何外部操作
```

### 5.3 数据安全

```
commit-guide:
  - 不将 diff 内容发送给 AI（仅发送 type + scope + 描述文本）
  - 不缓存或持久化 commit 内容

repo-analyzer:
  - 拉取的仓库数据仅在内存中处理，不落盘
  - AI 输入上下文不包含完整文件内容（仅 commit message / issue 标题 / PR 标题）
  - 生成的报告不包含敏感凭证信息
```

---

## 6. 错误处理策略

### 6.1 错误分类

| 类别 | 示例 | 处理策略 |
|---|---|---|
| 配置错误 | config.json 不存在 / 格式错误 | 终止运行，给出明确修复指引 |
| 认证错误 | API Key 无效 / Gitea Token 过期 | 终止运行，提示检查凭证 |
| 网络错误 | API 超时 / Gitea 不可达 | 重试 3 次（指数退避），仍失败则降级 |
| 数据错误 | commit message 格式不规范 | 降级处理，标记为 "未分类"，不崩溃 |
| 环境错误 | 不在 Git 仓库中 / git 未安装 | 终止运行，提示环境要求 |

### 6.2 降级策略

```
commit-guide 降级:
  AI 不可用 → 退化为纯交互模式（无润色建议）
  程序仍可正常完成 commit

repo-analyzer 降级:
  AI 不可用 → 输出原始数据摘要（统计表格）
  Gitea API 部分失败 → 仅输出成功拉取的数据
  commit 格式不规范 → 归入 "未分类" 类别
```

### 6.3 重试机制

```
网络请求重试策略:
  - 最大重试次数: 3
  - 退避策略: 指数退避 (1s → 2s → 4s)
  - 可重试错误: 超时 / 5xx 服务端错误 / 连接重置
  - 不可重试错误: 4xx 客户端错误（401/403/404）
```

---

## 7. 日志与监控

### 7.1 日志规范

```
日志级别:
  DEBUG   - 详细的调试信息（API 请求/响应摘要）
  INFO    - 关键流程节点（开始/完成/降级）
  WARNING - 可恢复的异常（重试成功 / 格式不规范降级）
  ERROR   - 不可恢复的错误（配置错误 / 认证失败）

日志格式:
  [时间戳] [级别] [模块] 消息内容

日志输出:
  - 默认输出到 stderr（与正常输出分离）
  - 可通过 --log-file 指定日志文件路径
```

### 7.2 关键监控指标

```
commit-guide:
  - 每次引导完成的耗时
  - AI 润色调用次数 / 成功率
  - 降级为纯交互模式的次数

repo-analyzer:
  - Gitea API 调用次数 / 成功率 / 延迟
  - AI 分析调用耗时
  - 降级输出次数
  - commit 格式识别率（规范格式占比）
```

---

## 8. 测试策略

### 8.1 测试层次

```
┌─────────────────────────────────┐
│         E2E 测试 (端到端)         │
│  完整流程: commit-guide → push   │
│  → repo-analyzer → 报告验证      │
├─────────────────────────────────┤
│        集成测试                   │
│  AI 调用集成 / Gitea API 集成    │
│  Git 操作集成 / 配置加载集成      │
├─────────────────────────────────┤
│        单元测试                   │
│  各模块独立测试 / Mock 外部依赖   │
└─────────────────────────────────┘
```

### 8.2 测试用例覆盖

```
commit-guide:
  □ 正常交互流程（选择 type → 输入 scope → 输入描述 → 确认提交）
  □ AI 润色可用时的完整流程
  □ AI 不可用时的降级流程
  □ 不在 Git 仓库中运行时的错误提示
  □ 无暂存文件时的提示
  □ 用户取消操作的处理
  □ 各种 commit type 组合的 message 格式验证

repo-analyzer:
  □ 正常拉取数据并生成 AI 摘要
  □ AI 不可用时输出原始数据摘要
  □ Gitea API 部分失败时的降级输出
  □ 空仓库（无 commit）的处理
  □ commit 格式全部不规范时的降级分类
  □ 混合格式（部分规范 + 部分不规范）的分类
  □ Markdown 文件输出
  □ 不同 --days 参数的数据范围
```

---

## 9. 部署方案

### 9.1 commit-guide 部署

```
部署方式: 本地安装
  - 克隆项目仓库到本地
  - 安装 Python 3.10+ 依赖
  - 配置 config.json（如需 AI 润色功能）
  - 将 commit-guide 目录加入 PATH 或使用别名

使用方式:
  $ cd /path/to/project
  $ python commit-guide/main.py
```

### 9.2 repo-analyzer 部署

```
部署方式 A: 管理者本地运行
  - 同 commit-guide 的本地安装步骤
  - 额外设置环境变量 GITEA_TOKEN

部署方式 B: 服务器定时任务
  - 服务器安装 Python 3.10+ 及依赖
  - 配置 cron / scheduled task
  - 示例 cron (每日 9:00):
    0 9 * * * cd /opt/repo-analyzer && \
    GITEA_TOKEN=xxx python main.py \
    --repo-url https://gitea.example.com/team/project \
    --days 1 --output report.md
```

---

## 10. 扩展性设计

### 10.1 预留扩展点

| 扩展点 | 当前状态 | 未来方向 |
|---|---|---|
| commit type 词汇表 | 8 种固定类型 | 支持自定义 type 配置文件 |
| AI 模型 | 单一 default_chat_model | 支持按场景指定不同模型 |
| 输出格式 | 终端 / Markdown | JSON / HTML / PDF |
| 数据来源 | Gitea API | GitLab / GitHub API 适配器 |
| 分析维度 | commit 分类 + issue/PR 状态 | 代码质量 / 测试覆盖率 / 部署频率 |
| 通知渠道 | 终端输出 | 飞书 / 钉钉 / 邮件推送 |

### 10.2 插件化方向

```
未来可考虑:
  - Analyzer Plugin: 自定义分析维度插件
  - Output Plugin: 自定义输出格式插件
  - Source Plugin: 自定义数据源插件（GitLab / GitHub）
```

---

## 11. 开发里程碑

| 阶段 | 内容 | 产出 | 预计工期 |
|---|---|---|---|
| M1 | commit-guide 最小版本 | 纯交互模式可运行 | 2 天 |
| M2 | repo-analyzer 数据拉取 | Gitea API 封装完成 | 2 天 |
| M3 | AI 分析接入 | AI 摘要生成可用 | 2 天 |
| M4 | commit-guide AI 润色 | AI 辅助功能可用 | 1 天 |
| M5 | 两端联调 | 端到端流程验证通过 | 1 天 |
| M6 | 测试与文档 | 测试用例 + 使用文档 | 2 天 |

---

## 12. 附录

### 12.1 依赖清单

```
Python 依赖:
  - requests (HTTP 调用)
  - (标准库) json, os, sys, subprocess, argparse, logging, datetime, re

系统依赖:
  - Python 3.10+
  - Git 2.30+ (commit-guide)
  - 网络连接 (repo-analyzer)
```

### 12.2 参考文档

- [commit-guide 详细设计](./gitea-commit-guide-detailed.md)
- [repo-analyzer 详细设计](./gitea-repo-analyzer-detailed.md)
- [commit-guide 设计方案 (v0.1)](./gitea-commit-guide.md)
- [repo-analyzer 设计方案 (v0.1)](./gitea-repo-analyzer.md)
