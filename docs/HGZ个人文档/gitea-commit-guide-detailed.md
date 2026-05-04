# commit-guide：员工端提交引导程序 - 详细设计文档

版本：v1.0
日期：2026-05-02
负责人：HGZ

---

## 1. 文档概述

### 1.1 文档目的

本文档是 commit-guide 程序的详细设计文档，在 v0.1 设计方案的基础上，对交互流程、模块接口、状态机、AI 集成、异常处理、测试方案等进行全面细化。

### 1.2 设计目标

| 目标 | 描述 | 优先级 |
|---|---|---|
| 统一格式 | 产出的 commit message 严格遵循 `type(scope): 描述` 格式 | P0 |
| 低门槛 | 员工无需记忆规范，通过选择 + 填空完成提交 | P0 |
| 韧性 | AI 不可用时程序仍可正常完成提交 | P0 |
| 可分析 | 生成的 commit 可被 repo-analyzer 正确识别和分类 | P1 |
| AI 辅助 | 提供可选的润色建议，不替代员工决策 | P2 |

---

## 2. 交互流程详细设计

### 2.1 状态机

```
                    ┌─────────┐
                    │  START   │
                    └────┬─────┘
                         │
                         ▼
              ┌─────────────────────┐
              │  CHECK_ENV           │
              │  检测 Git 环境        │
              │  - 是否在 Git 仓库中   │
              │  - git 是否可用       │
              └─────────┬───────────┘
                        │
              ┌─────────┴───────────┐
              │ 失败                 │ 成功
              ▼                      ▼
    ┌─────────────────┐   ┌─────────────────────┐
    │  ERROR_EXIT      │   │  CHECK_STATUS        │
    │  输出错误信息并退出 │   │  检测仓库状态         │
    └─────────────────┘   │  - 暂存区文件列表      │
                          │  - 未暂存修改列表      │
                          │  - 未跟踪文件列表      │
                          └─────────┬───────────┘
                                    │
                          ┌─────────┴───────────┐
                          │ 无暂存文件            │ 有暂存文件
                          ▼                      ▼
                ┌─────────────────┐   ┌─────────────────────┐
                │  WARN_NO_STAGE   │   │  SELECT_TYPE         │
                │  提示无暂存文件    │   │  展示 commit type    │
                │  询问是否继续     │   │  列表供选择           │
                └────────┬────────┘   └─────────┬───────────┘
                         │                      │
                         │ 继续                  │ 用户选择 type
                         ▼                      ▼
                ┌──────────────────────────────────────────────┐
                │  INPUT_SCOPE                                   │
                │  输入 scope（可选，回车跳过）                     │
                │  提示: "请输入影响范围（模块名），回车跳过"         │
                └──────────────────────┬───────────────────────┘
                                       │
                                       ▼
                ┌──────────────────────────────────────────────┐
                │  INPUT_DESCRIPTION                            │
                │  输入简短描述                                    │
                │  提示: "请输入变更描述（一句话）"                  │
                │  校验: 非空，长度 5-100 字符                     │
                └──────────────────────┬───────────────────────┘
                                       │
                                       ▼
                ┌──────────────────────────────────────────────┐
                │  PREVIEW                                       │
                │  预览拼装后的 commit message                    │
                │  格式: type(scope): 描述                        │
                │  选项: [确认提交] [AI润色] [重新编辑] [取消]      │
                └──────────────────────┬───────────────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                  │
                    ▼                  ▼                  ▼
          ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
          │ CONFIRM       │  │ AI_POLISH     │  │ RE_EDIT       │
          │ 执行 git      │  │ 调用 AI 润色   │  │ 返回          │
          │ commit        │  │ 展示建议       │  │ INPUT_SCOPE   │
          └──────┬───────┘  └──────┬───────┘  └──────────────┘
                 │                 │
                 ▼                 ▼
          ┌──────────────┐  ┌──────────────┐
          │ SUCCESS       │  │ POLISH_PREVIEW│
          │ 输出成功信息   │  │ 展示润色前后   │
          │ 显示 commit   │  │ 对比           │
          │ SHA           │  │ [接受][拒绝]   │
          └──────────────┘  │ [重新润色]     │
                            └──────┬───────┘
                                   │
                          ┌────────┼────────┐
                          ▼        ▼        ▼
                    ┌────────┐ ┌────────┐ ┌──────────┐
                    │接受     │ │拒绝     │ │重新润色   │
                    │→CONFIRM│ │→PREVIEW│ │→AI_POLISH│
                    └────────┘ └────────┘ └──────────┘
```

### 2.2 交互界面示例

```
═══════════════════════════════════════════════════════════
                    commit-guide v1.0
═══════════════════════════════════════════════════════════

📂 当前仓库: my-project
🌿 当前分支: feature/user-auth

暂存区文件 (3):
  ✓ src/auth/login.py
  ✓ src/auth/middleware.py
  ✓ tests/test_auth.py

───────────────────────────────────────────────────────────
请选择本次提交类型:

  [1] feat      新功能
  [2] fix       修复 bug
  [3] refactor  重构（不改功能）
  [4] docs      文档变更
  [5] test      测试相关
  [6] chore     构建、依赖、配置等杂项
  [7] perf      性能优化
  [8] revert    回滚

请输入序号 (1-8): 1

───────────────────────────────────────────────────────────
请输入影响范围（模块名），回车跳过:
> auth

───────────────────────────────────────────────────────────
请输入变更描述（一句话，5-100 字符）:
> 新增 JWT 登录接口

───────────────────────────────────────────────────────────
预览 commit message:

  feat(auth): 新增 JWT 登录接口

  [1] 确认提交
  [2] AI 润色建议
  [3] 重新编辑
  [4] 取消

请选择 (1-4):
```

---

## 3. 模块详细设计

### 3.1 main.py - 入口与交互主流程

```
职责:
  - 程序入口
  - 状态机驱动
  - 用户交互 I/O
  - 流程编排

核心类/函数:

  class CommitGuideApp:
      """交互主流程控制器"""

      def __init__(self):
          self.state = AppState.CHECK_ENV
          self.commit_type: Optional[str] = None
          self.scope: Optional[str] = None
          self.description: Optional[str] = None
          self.ai_available: bool = False

      def run(self) -> int:
          """主循环，返回退出码 (0=成功, 1=失败)"""
          ...

      def _handle_check_env(self) -> None:
          """检测 Git 环境"""
          ...

      def _handle_check_status(self) -> None:
          """检测仓库状态并展示文件列表"""
          ...

      def _handle_select_type(self) -> None:
          """展示 type 列表并获取用户选择"""
          ...

      def _handle_input_scope(self) -> None:
          """获取 scope 输入"""
          ...

      def _handle_input_description(self) -> None:
          """获取描述输入并校验"""
          ...

      def _handle_preview(self) -> None:
          """预览 message 并获取用户决策"""
          ...

      def _handle_ai_polish(self) -> None:
          """调用 AI 润色并展示建议"""
          ...

      def _handle_confirm(self) -> None:
          """执行 git commit"""
          ...

  class AppState(Enum):
      CHECK_ENV = "check_env"
      CHECK_STATUS = "check_status"
      SELECT_TYPE = "select_type"
      INPUT_SCOPE = "input_scope"
      INPUT_DESCRIPTION = "input_description"
      PREVIEW = "preview"
      AI_POLISH = "ai_polish"
      POLISH_PREVIEW = "polish_preview"
      CONFIRM = "confirm"
      SUCCESS = "success"
      ERROR_EXIT = "error_exit"
      CANCELLED = "cancelled"

入口:
  def main():
      app = CommitGuideApp()
      sys.exit(app.run())
```

### 3.2 types.py - Commit Type 定义与词汇表

```
职责:
  - 定义 commit type 枚举
  - 提供 type 的中文描述
  - 提供 type 列表查询接口
  - 校验 type 合法性

核心类/函数:

  @dataclass
  class CommitType:
      key: str          # "feat"
      description: str  # "新功能"
      emoji: str        # "✨" (仅展示用，不写入 commit)

  COMMIT_TYPES: List[CommitType] = [
      CommitType("feat",     "新功能",                       "✨"),
      CommitType("fix",      "修复 bug",                     "🐛"),
      CommitType("refactor", "重构（不改功能）",               "♻️"),
      CommitType("docs",     "文档变更",                      "📝"),
      CommitType("test",     "测试相关",                      "✅"),
      CommitType("chore",    "构建、依赖、配置等杂项",          "🔧"),
      CommitType("perf",     "性能优化",                      "⚡"),
      CommitType("revert",   "回滚",                         "⏪"),
  ]

  def get_commit_types() -> List[CommitType]:
      """返回所有 commit type"""
      return COMMIT_TYPES

  def get_type_by_key(key: str) -> Optional[CommitType]:
      """根据 key 查找 CommitType"""
      ...

  def is_valid_type(key: str) -> bool:
      """校验 type 是否合法"""
      ...

  def format_commit_message(
      type_key: str,
      scope: Optional[str],
      description: str
  ) -> str:
      """拼装标准 commit message
      返回: "type(scope): description" 或 "type: description"
      """
      ...
```

### 3.3 git_utils.py - Git 操作封装

```
职责:
  - 检测 Git 环境
  - 获取仓库状态
  - 执行 git commit
  - 所有 git 操作通过 subprocess 调用

核心类/函数:

  @dataclass
  class GitStatus:
      repo_name: str
      branch: str
      staged: List[str]       # 暂存区文件
      unstaged: List[str]     # 未暂存修改
      untracked: List[str]    # 未跟踪文件
      has_staged: bool        # 是否有暂存文件

  @dataclass
  class CommitResult:
      success: bool
      sha: Optional[str]      # 提交后的 commit SHA
      error_message: Optional[str]

  def check_git_available() -> bool:
      """检测 git 命令是否可用
      执行: git --version
      """
      ...

  def is_git_repo(path: str = ".") -> bool:
      """检测当前目录是否在 Git 仓库中
      执行: git rev-parse --git-dir
      """
      ...

  def get_repo_status(path: str = ".") -> GitStatus:
      """获取仓库状态
      执行:
        git rev-parse --abbrev-ref HEAD  → branch
        git diff --name-only --cached     → staged
        git diff --name-only              → unstaged
        git ls-files --others --exclude-standard → untracked
      """
      ...

  def execute_commit(message: str, path: str = ".") -> CommitResult:
      """执行 git commit
      使用 subprocess 列表形式传参，无需手动转义特殊字符，
      且避免 shell 注入风险:
        subprocess.run(["git", "commit", "-m", message], ...)
      """
      ...

  def get_last_commit_sha(path: str = ".") -> Optional[str]:
      """获取最新 commit SHA
      执行: git rev-parse HEAD
      """
      ...
```

### 3.4 ai_assist.py - AI 润色模块

```
职责:
  - 调用 AI 模型对 commit 描述进行润色
  - 提供润色建议，不自动应用
  - AI 不可用时优雅降级

核心类/函数:

  @dataclass
  class PolishResult:
      success: bool
      original: str           # 原始描述
      suggestion: str         # 润色建议
      reason: str             # 润色理由

  class AIPolisher:
      """AI 润色器"""

      def __init__(self):
          self.available: bool = False
          self.model_config: Optional[dict] = None
          self._init_ai()

      def _init_ai(self) -> None:
          """初始化 AI 连接
          1. 尝试加载 config.json
          2. 获取 default_chat_model 配置
          3. 验证 api_base 可达（可选健康检查）
          失败 → self.available = False
          """
          ...

      def is_available(self) -> bool:
          return self.available

      def polish(
          self,
          commit_type: str,
          scope: Optional[str],
          description: str
      ) -> PolishResult:
          """润色 commit 描述

          System Prompt:
            你是一个 commit message 润色助手。
            你的任务是优化 commit 描述，使其更清晰、简洁、专业。
            规则:
            1. 保持原意不变
            2. 使用中文
            3. 控制在 5-100 字符
            4. 不要添加 type 和 scope
            5. 只输出润色后的文本，不要解释

          User Message:
            类型: {commit_type}
            范围: {scope or "无"}
            原始描述: {description}

            请润色以上描述。

          异常处理:
            - 网络错误 → 返回 success=False
            - API 错误 → 返回 success=False
            - 响应解析失败 → 返回 success=False
          """
          ...

  def check_ai_availability() -> bool:
      """快速检查 AI 是否可用（供 main.py 初始化时调用）"""
      ...
```

### 3.5 config_loader.py - 配置加载

```
职责:
  - 定位并加载 config.json
  - 提供模型配置查询接口
  - 配置校验

核心函数:

  def find_project_root() -> Path:
      """查找项目根目录
      策略:
        1. 检查环境变量 PROJECT_ROOT
        2. 从当前文件向上查找包含 config.json 的目录
        3. 最多向上查找 5 层
      返回: 项目根目录 Path
      异常: FileNotFoundError - 未找到
      """
      ...

  def load_config() -> dict:
      """加载并校验 config.json
      返回: 完整配置字典
      异常:
        FileNotFoundError - config.json 不存在
        ValueError - JSON 格式错误或必填字段缺失
      """
      ...

  def get_default_model_config() -> dict:
      """获取默认模型配置
      从 config["models"][config["default_chat_model"]] 读取
      返回: {api_base, api_key, model, api_style}
      注意: api_base 已包含完整路径，直接用于 HTTP 请求
      """
      ...
```

> **MVP 阶段**：commit-guide 和 repo-analyzer 各自独立复制一份 `config_loader.py`，不抽取共享模块。后续两个程序稳定后再考虑抽取到公共目录。

---

## 4. Commit Message 格式规范

### 4.1 格式定义

```
完整格式:  type(scope): 描述
简化格式:  type: 描述

正则表达式: ^(feat|fix|refactor|docs|test|chore|perf|revert)(\([^)]+\))?: .{5,100}$

组成部分:
  type      - 必填，8 种之一
  scope     - 可选，括号包裹，模块名（英文/数字/连字符/下划线）
  冒号+空格  - 必填分隔符
  描述       - 必填，5-100 字符，中文/英文均可
```

### 4.2 示例

```
✓ feat(auth): 新增 JWT 登录接口
✓ fix: 修复用户列表分页错误
✓ refactor(api): 重构请求拦截器
✓ docs: 更新 API 接口文档
✓ test(user): 补充用户模块单元测试
✓ chore: 升级依赖版本
✓ perf(db): 优化数据库查询性能
✓ revert: 回滚 feat(auth) 提交

✗ add login feature          (缺少 type 前缀)
✗ feat:                      (缺少描述)
✗ feat(auth): 修             (描述少于 5 字符)
✗ feature(auth): 新增登录     (type 不在词汇表中)
```

---

## 5. 异常处理详细设计

### 5.1 异常场景与处理

| 场景 | 检测方式 | 处理 | 用户提示 |
|---|---|---|---|
| git 未安装 | `git --version` 失败 | 终止 | "未检测到 Git，请先安装 Git 2.30+" |
| 不在 Git 仓库中 | `git rev-parse --git-dir` 失败 | 终止 | "当前目录不是 Git 仓库，请在仓库目录下运行" |
| 无暂存文件 | staged 列表为空 | 警告 + 询问 | "暂存区为空，请先使用 git add 暂存文件。是否仍要继续？" |
| 描述为空 | 用户输入为空 | 重新输入 | "描述不能为空，请重新输入" |
| 描述过短 (<5字符) | 输入长度 < 5 | 重新输入 | "描述过短（至少 5 个字符），请重新输入" |
| 描述过长 (>100字符) | 输入长度 > 100 | 截断提示 | "描述过长，已截断为 100 字符" |
| config.json 不存在 | 文件读取失败 | 降级 | "config.json 未找到，AI 润色功能不可用" |
| AI API 超时 | 请求超时 | 降级 | "AI 服务响应超时，已切换为纯交互模式" |
| AI API 认证失败 | 401 状态码 | 降级 | "AI API 认证失败，请检查 config.json 中的 api_key" |
| git commit 失败 | subprocess 返回非 0 | 终止 | 显示 git 原始错误信息 |
| 用户取消操作 | 用户选择取消 | 正常退出 | "已取消提交" |

### 5.2 降级路径

```
正常路径:
  CHECK_ENV → CHECK_STATUS → SELECT_TYPE → INPUT_SCOPE
  → INPUT_DESCRIPTION → PREVIEW → [AI_POLISH] → CONFIRM → SUCCESS

AI 不可用降级:
  CHECK_ENV → CHECK_STATUS → SELECT_TYPE → INPUT_SCOPE
  → INPUT_DESCRIPTION → PREVIEW → CONFIRM → SUCCESS
  (PREVIEW 中不显示 AI 润色选项)

AI 调用失败降级:
  ... → PREVIEW → AI_POLISH → (失败) → PREVIEW
  (回到 PREVIEW，显示 "AI 润色暂时不可用" 提示)
```

---

## 6. 接口规范

### 6.1 命令行接口

```
用法:
  python main.py [选项]

选项:
  -h, --help          显示帮助信息
  -v, --version       显示版本号
  --no-ai             禁用 AI 润色功能
  --path PATH         指定 Git 仓库路径（默认当前目录）
  --dry-run           预览模式，不实际执行 commit

退出码:
  0 - 成功提交
  1 - 用户取消或环境错误
  2 - Git 操作失败
```

### 6.2 模块间接口

```
main.py → types.py:
  get_commit_types() → List[CommitType]
  is_valid_type(key) → bool
  format_commit_message(type, scope, desc) → str

main.py → git_utils.py:
  check_git_available() → bool
  is_git_repo(path) → bool
  get_repo_status(path) → GitStatus
  execute_commit(message, path) → CommitResult

main.py → ai_assist.py:
  check_ai_availability() → bool
  AIPolisher.polish(type, scope, desc) → PolishResult

main.py → config_loader.py:
  load_config() → dict
  get_default_model_config() → dict
```

---

## 7. 测试方案

### 7.1 单元测试

```
test_types.py:
  □ test_get_commit_types_returns_all_8_types
  □ test_is_valid_type_with_valid_key
  □ test_is_valid_type_with_invalid_key
  □ test_format_commit_message_with_scope
  □ test_format_commit_message_without_scope
  □ test_format_commit_message_empty_scope

test_git_utils.py:
  □ test_check_git_available_success (mock subprocess)
  □ test_check_git_available_failure (mock subprocess)
  □ test_is_git_repo_true (mock subprocess)
  □ test_is_git_repo_false (mock subprocess)
  □ test_get_repo_status (mock subprocess)
  □ test_execute_commit_success (mock subprocess)
  □ test_execute_commit_failure (mock subprocess)
  □ test_execute_commit_escapes_quotes

test_ai_assist.py:
  □ test_polish_success (mock HTTP response)
  □ test_polish_network_error
  □ test_polish_api_error
  □ test_polish_auth_error
  □ test_init_ai_config_not_found
  □ test_init_ai_config_invalid

test_config_loader.py:
  □ test_load_config_success
  □ test_load_config_file_not_found
  □ test_load_config_invalid_json
  □ test_load_config_missing_default_model
  □ test_get_default_model_config
  □ test_find_project_root_from_env
  □ test_find_project_root_auto_detect
```

### 7.2 集成测试

```
test_integration.py:
  □ test_full_flow_without_ai (模拟用户输入序列)
  □ test_full_flow_with_ai_success
  □ test_full_flow_ai_unavailable_fallback
  □ test_flow_user_cancels_at_preview
  □ test_flow_user_reedit_from_preview
  □ test_flow_no_staged_files_warning
  □ test_flow_invalid_description_retry
```

### 7.3 E2E 测试

```
test_e2e.py:
  □ 在临时 Git 仓库中运行完整流程
  □ 验证生成的 commit message 格式
  □ 验证 commit 存在于 git log 中
  □ 验证 repo-analyzer 可正确识别该 commit 的 type
```

---

## 8. 附录

### 8.1 文件清单

```
commit-guide/
  __init__.py
  main.py              (~250 行) 入口 + 状态机 + 交互
  types.py             (~60 行)  CommitType 定义 + 格式化
  git_utils.py         (~120 行) Git 操作封装
  ai_assist.py         (~100 行) AI 润色调用
  config_loader.py     (~80 行)  配置加载
```

### 8.2 依赖

```
标准库: sys, os, subprocess, enum, dataclasses, typing, re
第三方: requests (仅 ai_assist.py 需要)
```
