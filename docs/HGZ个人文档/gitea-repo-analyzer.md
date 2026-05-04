# repo-analyzer：管理者端 Gitea 仓库 AI 分析程序

版本：v0.1  
日期：2026-05-02  
负责人：HGZ

---

## 1. 目标

管理者或项目负责人指定一个 Gitea 仓库，程序自动拉取近期开发数据，用 AI 生成可读的项目状态摘要。

核心输出：

- 近期做了什么（按 commit type 分类）
- 当前有哪些未关闭的问题（issues / PRs）
- 识别出的风险或值得关注的信号
- 建议的下一步

---

## 2. 数据来源

从 Gitea API 拉取以下内容：

| 数据 | 用途 |
|---|---|
| 近期 commits（可指定分支和时间范围） | 了解开发进展，依赖 commit-guide 的统一格式做分类 |
| 开放的 issues | 了解已知问题和待办 |
| 开放的 PRs | 了解正在进行的工作和代码审查状态 |
| 分支列表 | 了解并行开发情况 |

Gitea API 调用参考 `funkyape/general_agent/skills/gitea-repo-api/scripts/gitea_api.py`，可直接复用其 HTTP 调用和参数处理逻辑。

Gitea token 通过环境变量 `GITEA_TOKEN` 传入。

---

## 3. AI 分析策略

拉取数据后，组装成结构化上下文，交给 AI 生成摘要。

关键点：
- commit message 如果遵循 commit-guide 的格式，AI 可以按 type 分类统计，分析更准确
- issues 和 PRs 的标题 + 状态是主要输入，不需要拉取全文
- AI 输出要区分事实（来自数据）和推断（AI 判断），避免把推断当事实呈现

AI 调用从 `config.json` 读取，使用 `default_chat_model` 指定的模型。

---

## 4. 运行方式

命令行调用，指定仓库和分析范围：

```
python main.py --repo-url https://gitea.example.com/owner/repo
python main.py --repo-url ... --days 7 --branch main
```

输出到终端，可选输出到 Markdown 文件。

---

## 5. 目录结构方向

```
repo-analyzer/
  main.py           入口，参数解析和流程控制
  gitea_client.py   封装 Gitea API 调用（参考 gitea_api.py）
  data_builder.py   把拉取的数据组装成 AI 输入上下文
  analyzer.py       调用 AI，生成结构化摘要
  config_loader.py  读取 config.json
  output.py         格式化输出（终端 / Markdown）
```

---

## 6. 输出结构方向

```
## 项目状态摘要 - {repo} - {date}

### 近期开发活动（最近 N 天）
- feat: X 条（新功能）
- fix: Y 条（修复）
- ...

### 开放问题
- {issue 标题} - 已开放 N 天

### 开放 PR
- {PR 标题} - 等待审查 / 等待合并

### 风险信号
- ...（AI 推断，标注为推断）

### 建议关注
- ...
```

---

## 7. 验收方向

- 指定仓库 URL 后能自动拉取数据并生成摘要
- commit 分类依赖 commit-guide 的 type 格式，格式不规范时能降级处理（不崩溃）
- AI 不可用时能输出原始数据摘要
- 输出内容区分事实和推断
