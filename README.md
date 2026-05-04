# AgentOS

公司的 AI 操作系统——用工作流自动化推动组织运转，用共事 Agent 帮员工把想法落地，用组织记忆让公司越工作越聪明。

## 项目文档

| 文档 | 说明 |
|------|------|
| [项目背景](./项目背景.md) | 为什么做、解决什么问题、关键约束 |
| [项目目的](./项目目的.md) | 核心目标、MVP 范围、成功指标 |
| [项目进度](./项目进度.md) | 当前阶段、模块状态、最近提交、下一步计划 |
| [产品设计](./agentos-product-design.md) | 完整产品设计文档 v0.1 |

## 模块结构

```
src/
├── agent_engine/    # Agent 编排引擎（模式路由、风险分类、记忆管理）
├── commit_guide/    # CLI 智能提交工具（AI 读 diff → commit message）
└── repo_analyzer/   # Gitea 仓库分析（代码上下文、历史、PR/Issue）
```

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 智能提交
cd src && python -m commit_guide.main

# 仓库分析
cd src && python -m repo_analyzer.main --repo <org/repo>
```

## 技术栈

- **语言**：Python 3.10+
- **AI 模型**：DeepSeek 系列
- **代码托管**：自建 Gitea 实例
- **依赖管理**：pip + requirements.txt

## 开发团队

- **HGZ**（黄龚智）：agent_engine、commit_guide、repo_analyzer
- **ZSS**：前端与产品工程
- 其余角色见 `docs/development-plans/`
