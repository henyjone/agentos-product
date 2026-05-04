# commit-guide：员工端提交引导程序

版本：v0.1  
日期：2026-05-02  
负责人：HGZ

---

## 1. 目标

解决一个具体问题：每个人写 commit message 的方式不一样，导致管理者 AI 分析时词汇混乱、难以归类。

commit-guide 不强制员工记住规范，而是通过交互引导，让员工自然地产出格式统一的 commit message。

---

## 2. 核心交互流程

```
启动 commit-guide
  └── 检测当前 git 仓库状态（有哪些改动文件）
  └── 引导员工选择本次提交的类型
  └── 引导员工填写简短描述
  └── （可选）AI 辅助润色或补全描述
  └── 预览最终 commit message
  └── 确认后执行 git commit
```

员工不需要记住格式，程序负责拼装。

---

## 3. 统一词汇表（commit type）

这是系统的核心约定，管理者端 AI 依赖这套词汇做分类分析。

| type | 含义 |
|---|---|
| `feat` | 新功能 |
| `fix` | 修复 bug |
| `refactor` | 重构（不改功能） |
| `docs` | 文档变更 |
| `test` | 测试相关 |
| `chore` | 构建、依赖、配置等杂项 |
| `perf` | 性能优化 |
| `revert` | 回滚 |

格式：`type(scope): 描述`  
示例：`feat(auth): 新增 JWT 登录接口`

scope 可选，填模块名或留空。

---

## 4. AI 辅助的使用方式

AI 不替员工写 commit，而是在员工填完描述后，提供一个"润色建议"供参考。

员工可以接受、修改或忽略建议。

AI 调用从 `config.json` 读取，使用 `default_chat_model` 指定的模型。  
如果 AI 不可用，程序退化为纯交互模式，不影响正常使用。

---

## 5. 程序边界

- 只负责生成 commit message 并执行 `git commit`
- 不负责 `git add`（员工自己决定暂存哪些文件）
- 不负责 `git push`（员工自己决定何时推送）
- 不连接 Gitea API

---

## 6. 目录结构方向

```
commit-guide/
  main.py          入口，交互主流程
  types.py         commit type 定义和词汇表
  git_utils.py     git 状态检测、执行 commit
  ai_assist.py     AI 润色调用（可选模块）
  config_loader.py 读取 config.json
```

---

## 7. 验收方向

- 员工不需要手动输入 type 字符串，只需选择
- 最终 commit message 格式符合约定
- AI 不可用时程序仍然可以正常完成提交
- 生成的 commit 在 Gitea 上可被 repo-analyzer 正确识别和分类
