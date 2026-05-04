# Gitea AI 分析系统 - 统筹规划

版本：v0.1  
日期：2026-05-02  
负责人：HGZ

---

## 1. 背景与目标

管理者需要了解团队的真实开发状态，但直接读 commit 记录效率低、信息散。  
员工提交时缺乏统一规范，导致 AI 分析时词汇混乱、难以归类。

本系统用两个独立程序解决这两个问题，形成一套闭环：

> 员工用统一词汇提交 → 管理者 AI 读取并分析 → 输出可信的项目状态摘要

---

## 2. 两个程序

| 程序 | 面向 | 核心功能 |
|---|---|---|
| **commit-guide**（员工端） | 开发者 | 引导员工写出格式统一的 commit message |
| **repo-analyzer**（管理者端） | 管理者 / 项目负责人 | 读取 Gitea 仓库内容，用 AI 生成项目状态摘要 |

两个程序独立运行，不互相调用。  
员工端的价值在于提升管理者端的分析质量。

---

## 3. 系统关系图

```
员工本地
  └── commit-guide
        └── 引导填写标准化 commit message
        └── git commit（本地执行）
        └── git push 到 Gitea

Gitea 仓库
  └── commits / issues / PRs / branches

管理者本地 / 服务器
  └── repo-analyzer
        └── 调用 Gitea API 拉取仓库数据
        └── 调用 AI 模型生成摘要
        └── 输出项目状态报告
```

---

## 4. 配置约定

所有需要调用 AI 模型的地方，统一从项目根目录的 `config.json` 读取配置。

```
D:\pro\agentos-product\config.json
```

读取方式：加载 `models` 字段，默认使用 `default_chat_model` 指定的模型。  
两个程序都遵守这个约定，不硬编码 API key 或模型名。

Gitea 访问 token 通过环境变量 `GITEA_TOKEN` 传入，不写入配置文件。

---

## 5. 技术选型方向

- 语言：Python 3.10+
- AI 调用：openai-compatible 接口（config.json 中所有模型均为此格式）
- Gitea 数据获取：参考 `funkyape/general_agent/skills/gitea-repo-api/scripts/gitea_api.py`，可直接复用或裁剪
- 输出格式：终端可读文本为主，后续可扩展为 JSON / Markdown 文件

---

## 6. 开发顺序建议

1. 先跑通 commit-guide 的最小版本（本地无需 AI 也能用）
2. 再跑通 repo-analyzer 的 Gitea 数据拉取部分
3. 接入 AI 生成摘要
4. 两端联调：用 commit-guide 提交几条标准 commit，再用 repo-analyzer 分析，验证分析质量是否提升

---

## 7. 文档索引

- [commit-guide 设计方案](./gitea-commit-guide.md)
- [repo-analyzer 设计方案](./gitea-repo-analyzer.md)
