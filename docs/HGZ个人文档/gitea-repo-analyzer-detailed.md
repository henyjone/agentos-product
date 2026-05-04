# repo-analyzer：管理者端 Gitea 仓库 AI 分析程序 - 详细设计文档

版本：v1.0
日期：2026-05-02
负责人：HGZ

---

## 1. 文档概述

### 1.1 文档目的

本文档是 repo-analyzer 程序的详细设计文档，在 v0.1 设计方案的基础上，对 Gitea API 集成、数据组装策略、AI Prompt 工程、输出格式化、异常降级、性能优化、测试方案等进行全面细化。

### 1.2 设计目标

| 目标 | 描述 | 优先级 |
|---|---|---|
| 自动拉取 | 指定仓库 URL 后自动拉取 commits / issues / PRs / branches | P0 |
| 智能分类 | 按 commit-guide 标准格式对 commit 进行 type 分类统计 | P0 |
| AI 摘要 | 用 AI 生成可读的项目状态摘要 | P0 |
| 韧性降级 | AI 不可用或 API 部分失败时能输出原始数据摘要 | P0 |
| 事实推断分离 | 输出明确区分事实（来自数据）和推断（AI 判断） | P1 |
| 风险识别 | 自动识别值得关注的信号（长期未关闭 issue、大量并行分支等） | P1 |

---

## 2. 系统流程详细设计

### 2.1 主流程

```
                    ┌─────────┐
                    │  START   │
                    └────┬─────┘
                         │
                         ▼
              ┌─────────────────────┐
              │  PARSE_ARGS          │
              │  解析命令行参数        │
              │  --repo-url (必填)    │
              │  --days (默认 7)      │
              │  --branch (默认 main) │
              │  --output (可选)      │
              │  --no-ai (可选)       │
              └─────────┬───────────┘
                        │
                        ▼
              ┌─────────────────────┐
              │  VALIDATE_INPUT      │
              │  校验参数合法性        │
              │  - repo-url 格式      │
              │  - days > 0          │
              │  - GITEA_TOKEN 存在   │
              └─────────┬───────────┘
                        │
              ┌─────────┴───────────┐
              │ 校验失败              │ 校验通过
              ▼                      ▼
    ┌─────────────────┐   ┌─────────────────────┐
    │  ERROR_EXIT      │   │  LOAD_CONFIG         │
    │  输出错误并退出    │   │  加载 config.json     │
    └─────────────────┘   │  获取 AI 模型配置      │
                          └─────────┬───────────┘
                                    │
                                    ▼
              ┌──────────────────────────────────────────────┐
              │  FETCH_DATA (并行)                            │
              │                                               │
              │  ┌─────────────┐  ┌─────────────┐            │
              │  │ fetch_commits│  │ fetch_issues │            │
              │  └─────────────┘  └─────────────┘            │
              │  ┌─────────────┐  ┌─────────────┐            │
              │  │ fetch_prs    │  │ fetch_branches│           │
              │  └─────────────┘  └─────────────┘            │
              │                                               │
              │  每个调用独立重试，失败不阻塞其他调用            │
              └──────────────────────┬───────────────────────┘
                                     │
                                     ▼
              ┌──────────────────────────────────────────────┐
              │  CLASSIFY_COMMITS                             │
              │  对 commit message 进行 type 分类              │
              │  - 正则匹配标准格式 → 提取 type                │
              │  - 不匹配 → 归入 "uncategorized"              │
              └──────────────────────┬───────────────────────┘
                                     │
                                     ▼
              ┌──────────────────────────────────────────────┐
              │  BUILD_CONTEXT                                │
              │  组装 AI 输入上下文                             │
              │  - 统计摘要（各 type 数量）                     │
              │  - commit 列表（截断，最多 50 条）              │
              │  - issue 列表                                 │
              │  - PR 列表                                    │
              │  - 分支列表                                   │
              └──────────────────────┬───────────────────────┘
                                     │
                          ┌──────────┴──────────┐
                          │ --no-ai              │ 正常
                          ▼                      ▼
                ┌─────────────────┐   ┌─────────────────────┐
                │  RAW_OUTPUT      │   │  AI_ANALYZE          │
                │  输出原始数据摘要  │   │  调用 AI 生成摘要     │
                └────────┬────────┘   └─────────┬───────────┘
                         │                      │
                         │              ┌────────┴──────────┐
                         │              │ 成功                │ 失败
                         │              ▼                    ▼
                         │    ┌─────────────────┐  ┌─────────────────┐
                         │    │  FORMAT_OUTPUT   │  │  RAW_OUTPUT      │
                         │    │  格式化 AI 摘要   │  │  降级为原始输出   │
                         │    └────────┬────────┘  └────────┬────────┘
                         │             │                    │
                         └─────────────┴────────────────────┘
                                       │
                                       ▼
                              ┌─────────────────┐
                              │  RENDER           │
                              │  终端输出 / 写文件  │
                              └─────────────────┘
```

### 2.2 并行数据拉取策略

```
fetch_all_data(repo_url, branch, since):
    results = {}
    errors = []

    并行发起 4 个请求:
      thread_1: fetch_commits(repo_url, branch, since)
      thread_2: fetch_issues(repo_url, "open")
      thread_3: fetch_pull_requests(repo_url, "open")
      thread_4: fetch_branches(repo_url)

    等待所有线程完成 (超时 30s)

    收集结果:
      results["commits"] = thread_1.result or []
      results["issues"] = thread_2.result or []
      results["pull_requests"] = thread_3.result or []
      results["branches"] = thread_4.result or []

    记录错误:
      if thread_1.failed: errors.append("commits: {error}")
      ...

    return results, errors
```

---

## 3. 模块详细设计

### 3.1 main.py - 入口与流程控制

```
职责:
  - 命令行参数解析
  - 参数校验
  - 流程编排
  - 顶层异常捕获

核心函数:

  def parse_args() -> argparse.Namespace:
      parser = argparse.ArgumentParser(
          description="Gitea 仓库 AI 分析工具"
      )
      parser.add_argument(
          "--repo-url", required=True,
          help="Gitea 仓库完整 URL，如 https://gitea.example.com/owner/repo"
      )
      parser.add_argument(
          "--days", type=int, default=7,
          help="分析最近 N 天的数据 (默认 7)"
      )
      parser.add_argument(
          "--branch", default="main",
          help="目标分支 (默认 main)"
      )
      parser.add_argument(
          "--output", "-o", default=None,
          help="输出到 Markdown 文件路径"
      )
      parser.add_argument(
          "--no-ai", action="store_true",
          help="跳过 AI 分析，仅输出原始数据摘要"
      )
      parser.add_argument(
          "--max-commits", type=int, default=50,
          help="最多分析的 commit 数量 (默认 50)"
      )
      parser.add_argument(
          "--verbose", "-v", action="store_true",
          help="输出详细日志"
      )
      return parser.parse_args()

  def validate_args(args) -> None:
      if not args.repo_url.startswith("http"):
          raise ValueError("repo-url 必须以 http/https 开头")
      if args.days < 1:
          raise ValueError("days 必须大于 0")
      if not os.environ.get("GITEA_TOKEN"):
          raise ValueError("环境变量 GITEA_TOKEN 未设置")

  def main() -> int:
      try:
          args = parse_args()
          validate_args(args)
          setup_logging(args.verbose)

          config = load_config()
          model_config = get_default_model_config() if not args.no_ai else None

          results, errors = fetch_all_data(
              args.repo_url, args.branch, args.days
          )

          classified = classify_commits(results.get("commits", []))

          if args.no_ai or model_config is None:
              report = build_raw_report(
                  classified, results, errors, args
              )
          else:
              try:
                  context = build_analysis_context(
                      classified, results, args
                  )
                  analysis = run_ai_analysis(context, model_config)
                  report = format_ai_report(
                      analysis, classified, results, errors, args
                  )
              except AIAnalysisError:
                  logging.warning("AI 分析失败，降级为原始数据输出")
                  report = build_raw_report(
                      classified, results, errors, args
                  )

          render_report(report, args.output)
          return 0

      except Exception as e:
          logging.error(f"程序异常: {e}")
          return 1
```

### 3.2 gitea_client.py - Gitea API 封装

```
职责:
  - 封装 Gitea REST API 调用
  - 处理认证（GITEA_TOKEN）
  - 处理分页
  - 处理重试
  - 统一错误处理

核心类/函数:

  class GiteaClient:
      """Gitea API 客户端"""

      def __init__(self, base_url: str, token: str):
          self.base_url = base_url.rstrip("/")
          self.token = token
          self.session = requests.Session()
          self.session.headers.update({
              "Authorization": f"token {token}",
              "Accept": "application/json",
          })
          self.max_retries = 3
          self.timeout = 30

      def _request(
          self,
          method: str,
          path: str,
          params: dict = None
      ) -> dict | list:
          """统一请求方法，含重试逻辑"""
          url = f"{self.base_url}/api/v1{path}"
          for attempt in range(self.max_retries):
              try:
                  resp = self.session.request(
                      method, url, params=params,
                      timeout=self.timeout
                  )
                  if resp.status_code == 200:
                      return resp.json()
                  if resp.status_code == 404:
                      raise ResourceNotFoundError(f"资源不存在: {path}")
                  if resp.status_code == 401:
                      raise AuthError("GITEA_TOKEN 无效或已过期")
                  if resp.status_code == 403:
                      raise AuthError("GITEA_TOKEN 权限不足")
                  if resp.status_code >= 500:
                      if attempt < self.max_retries - 1:
                          wait = 2 ** attempt
                          time.sleep(wait)
                          continue
                      raise APIError(f"服务器错误: {resp.status_code}")
                  raise APIError(f"API 错误: {resp.status_code} {resp.text}")
              except requests.Timeout:
                  if attempt < self.max_retries - 1:
                      wait = 2 ** attempt
                      time.sleep(wait)
                      continue
                  raise NetworkError("请求超时")
              except requests.ConnectionError:
                  if attempt < self.max_retries - 1:
                      wait = 2 ** attempt
                      time.sleep(wait)
                      continue
                  raise NetworkError("无法连接到 Gitea 服务器")

      def _paginate(self, path: str, params: dict = None) -> list:
          """处理分页，获取全部结果"""
          all_items = []
          page = 1
          per_page = 50
          while True:
              paged_params = (params or {}).copy()
              paged_params["page"] = page
              paged_params["limit"] = per_page
              items = self._request("GET", path, paged_params)
              if not items:
                  break
              all_items.extend(items if isinstance(items, list) else [items])
              if len(items) < per_page:
                  break
              page += 1
          return all_items

  def parse_repo_url(url: str) -> tuple:
      """解析仓库 URL，提取 owner 和 repo 名称
      输入: https://gitea.example.com/owner/repo
      输出: ("https://gitea.example.com", "owner", "repo")
      """
      ...

  def fetch_commits(
      client: GiteaClient,
      owner: str,
      repo: str,
      branch: str,
      since: str,
      max_count: int = 50
  ) -> List[dict]:
      """拉取 commit 列表
      API: GET /repos/{owner}/{repo}/commits
      参数: sha={branch}, since={ISO8601}, limit={max_count}
      返回字段: sha, commit.message, commit.author.name,
               commit.author.date, html_url
      """
      ...

  def fetch_issues(
      client: GiteaClient,
      owner: str,
      repo: str,
      state: str = "open"
  ) -> List[dict]:
      """拉取 issue 列表
      API: GET /repos/{owner}/{repo}/issues
      参数: state={state}
      返回字段: number, title, state, created_at, updated_at,
               labels, assignee.login
      """
      ...

  def fetch_pull_requests(
      client: GiteaClient,
      owner: str,
      repo: str,
      state: str = "open"
  ) -> List[dict]:
      """拉取 PR 列表
      API: GET /repos/{owner}/{repo}/pulls
      参数: state={state}
      返回字段: number, title, state, created_at, updated_at,
               user.login, draft, mergeable
      """
      ...

  def fetch_branches(
      client: GiteaClient,
      owner: str,
      repo: str
  ) -> List[dict]:
      """拉取分支列表
      API: GET /repos/{owner}/{repo}/branches
      返回字段: name, commit.id, commit.committer.date
      """
      ...
```

### 3.3 data_builder.py - 数据组装

```
职责:
  - 对 commit message 进行 type 分类
  - 生成统计摘要
  - 组装 AI 输入上下文文本
  - 控制上下文长度（避免超出 token 限制）

核心类/函数:

  @dataclass
  class ClassifiedCommit:
      sha: str
      full_message: str
      type: str              # "feat" / "uncategorized"
      scope: Optional[str]
      description: str
      author: str
      date: str

  @dataclass
  class CommitStats:
      total: int
      by_type: Dict[str, int]  # {"feat": 5, "fix": 3, ...}
      uncategorized: int
      format_compliance_rate: float  # 规范格式占比

  COMMIT_PATTERN = re.compile(
      r'^(feat|fix|refactor|docs|test|chore|perf|revert)'
      r'(\([^)]+\))?:\s*(.+)$'
  )

  def classify_commits(raw_commits: List[dict]) -> List[ClassifiedCommit]:
      """对 commit 列表进行分类"""
      classified = []
      for c in raw_commits:
          message = c.get("commit", {}).get("message", "")
          first_line = message.split("\n")[0].strip()
          match = COMMIT_PATTERN.match(first_line)
          if match:
              classified.append(ClassifiedCommit(
                  sha=c.get("sha", "")[:8],
                  full_message=first_line,
                  type=match.group(1),
                  scope=match.group(2).strip("()") if match.group(2) else None,
                  description=match.group(3).strip(),
                  author=c.get("commit", {}).get("author", {}).get("name", ""),
                  date=c.get("commit", {}).get("author", {}).get("date", ""),
              ))
          else:
              classified.append(ClassifiedCommit(
                  sha=c.get("sha", "")[:8],
                  full_message=first_line,
                  type="uncategorized",
                  scope=None,
                  description=first_line[:100],
                  author=c.get("commit", {}).get("author", {}).get("name", ""),
                  date=c.get("commit", {}).get("author", {}).get("date", ""),
              ))
      return classified

  def compute_stats(classified: List[ClassifiedCommit]) -> CommitStats:
      """计算分类统计"""
      by_type = {}
      uncategorized = 0
      for c in classified:
          if c.type == "uncategorized":
              uncategorized += 1
          else:
              by_type[c.type] = by_type.get(c.type, 0) + 1
      total = len(classified)
      compliance = (total - uncategorized) / total if total > 0 else 0
      return CommitStats(
          total=total,
          by_type=by_type,
          uncategorized=uncategorized,
          format_compliance_rate=compliance,
      )

  def build_analysis_context(
      classified: List[ClassifiedCommit],
      raw_data: dict,
      args
  ) -> str:
      """组装 AI 分析上下文

      结构:
        1. 项目基本信息（仓库、分支、时间范围）
        2. Commit 统计摘要（表格）
        3. Commit 详细列表（截断至 max_commits 条）
        4. 开放 Issue 列表
        5. 开放 PR 列表
        6. 活跃分支列表

      长度控制:
        - commit 列表最多 50 条
        - issue 列表最多 20 条
        - PR 列表最多 20 条
        - 分支列表最多 15 条
        - 总上下文控制在 4000 token 以内
      """
      ...
```

### 3.4 analyzer.py - AI 分析

```
职责:
  - 构建 System Prompt（要求 AI 输出 JSON）
  - 调用 AI 模型
  - json.loads 解析 AI 响应
  - 结构化输出

核心类/函数:

  SYSTEM_PROMPT = """你是一个专业的软件项目管理分析助手。
你的任务是根据提供的 Gitea 仓库数据，生成一份项目状态摘要。

分析要求:
1. 基于数据中的 commit 分类统计，总结近期开发活动
2. 关注开放 issue 和 PR 的状态，识别阻塞点
3. 识别潜在风险信号（如长期未关闭的 issue、大量并行分支等）
4. 给出建议的下一步关注点

重要: 请以 JSON 格式输出，不要输出任何其他内容。
输出结构如下:
{
  "summary": "项目状态摘要（Markdown 格式的完整摘要文本）",
  "facts": [
    "事实1（来自数据，不要编造）",
    "事实2"
  ],
  "inferences": [
    "推断1（AI 判断，非直接数据）",
    "推断2"
  ],
  "risks": [
    {"signal": "风险描述", "basis": "判断依据", "severity": "high|medium|low"},
  ],
  "suggestions": [
    "建议1（具体、可操作）",
    "建议2"
  ]
}
"""

  @dataclass
  class AnalysisResult:
      summary: str           # Markdown 摘要文本
      facts: List[str]       # 事实列表
      inferences: List[str]  # 推断列表
      risks: List[dict]      # [{signal, basis, severity}]
      suggestions: List[str] # 建议列表

  class AIAnalyzer:
      def __init__(self, model_config: dict):
          self.api_base = model_config["api_base"]
          self.api_key = model_config["api_key"]
          self.model = model_config["model"]

      def analyze(self, context: str) -> AnalysisResult:
          messages = [
              {"role": "system", "content": SYSTEM_PROMPT},
              {"role": "user", "content": context},
          ]
          response = self._call_api(messages)
          return self._parse_response(response)

      def _call_api(self, messages: list) -> str:
          """调用 openai-compatible API
          注意: api_base 已包含完整路径，直接使用，不拼接 /chat/completions
          """
          headers = {
              "Authorization": f"Bearer {self.api_key}",
              "Content-Type": "application/json",
          }
          payload = {
              "model": self.model,
              "messages": messages,
              "max_tokens": 4096,
              "temperature": 0.7,
          }
          resp = requests.post(
              self.api_base, headers=headers, json=payload, timeout=60
          )
          if resp.status_code != 200:
              raise AIAnalysisError(
                  f"AI API 返回错误: {resp.status_code} {resp.text[:200]}"
              )
          data = resp.json()
          return data["choices"][0]["message"]["content"]

      def _parse_response(self, raw: str) -> AnalysisResult:
          """解析 AI 的 JSON 响应为结构化结果

          AI 按 System Prompt 要求输出 JSON，直接 json.loads 即可。
          容错: 如果 AI 在 JSON 前后包裹了 ```json ... ```，
          先 strip 掉 markdown 代码块标记再解析。
          """
          text = raw.strip()
          if text.startswith("```"):
              lines = text.split("\n")
              lines = [l for l in lines if not l.startswith("```")]
              text = "\n".join(lines).strip()
          data = json.loads(text)
          return AnalysisResult(
              summary=data.get("summary", ""),
              facts=data.get("facts", []),
              inferences=data.get("inferences", []),
              risks=data.get("risks", []),
              suggestions=data.get("suggestions", []),
          )

  def run_ai_analysis(
      context: str,
      model_config: dict
  ) -> AnalysisResult:
      analyzer = AIAnalyzer(model_config)
      return analyzer.analyze(context)
```

### 3.5 output.py - 输出格式化

```
职责:
  - 格式化 AI 分析结果为终端可读文本
  - 生成 Markdown 文件
  - 生成原始数据摘要（降级模式）

核心函数:

  def format_ai_report(
      analysis: AnalysisResult,
      classified: List[ClassifiedCommit],
      raw_data: dict,
      errors: List[str],
      args
  ) -> str:
      """格式化 AI 分析报告

      结构:
        ═══════════════════════════════════
        项目状态摘要 - {repo} - {date}
        ═══════════════════════════════════

        {analysis.summary}

        ───────────────────────────────────
        数据概览
          分析范围: 最近 {days} 天, {branch} 分支
          Commit 总数: {total}
          格式规范率: {rate}%
          数据拉取错误: {errors or "无"}

        ───────────────────────────────────
        事实与推断标注
          事实 (来自数据):
            - ...
          推断 (AI 判断):
            - ...
      """
      ...

  def build_raw_report(
      classified: List[ClassifiedCommit],
      raw_data: dict,
      errors: List[str],
      args
  ) -> str:
      """构建原始数据摘要（AI 不可用时的降级输出）

      结构:
        ═══════════════════════════════════
        项目数据摘要 - {repo} - {date}
        ═══════════════════════════════════

        ## Commit 分类统计
        | Type | 数量 |
        |------|------|
        | feat | 5    |
        | fix  | 3    |
        ...

        ## 近期 Commit 列表
        - sha1 feat(auth): 新增 JWT 登录接口 (张三, 2026-05-01)
        ...

        ## 开放 Issue ({count})
        - #12 登录页面样式异常 (2026-04-28)

        ## 开放 PR ({count})
        - #34 重构用户模块 (张三, 2026-05-01)

        ## 分支列表
        - main (活跃)
        - feature/user-auth (活跃)
        ...
      """
      ...

  def render_report(report: str, output_path: Optional[str]) -> None:
      """渲染报告到终端或文件"""
      if output_path:
          with open(output_path, "w", encoding="utf-8") as f:
              f.write(report)
          print(f"报告已保存到: {output_path}")
      else:
          print(report)
```

### 3.6 config_loader.py - 配置加载

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
      """
      ...

  def load_config() -> dict:
      """加载并校验 config.json"""
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

## 4. Commit 分类策略

### 4.1 正则匹配

```
正则表达式:
  ^(feat|fix|refactor|docs|test|chore|perf|revert)(\([^)]+\))?:\s*(.+)$

匹配组:
  group(1): type     - feat / fix / refactor / docs / test / chore / perf / revert
  group(2): scope    - (auth) / (api) 等，含括号
  group(3): description - 描述文本

匹配示例:
  ✓ "feat(auth): 新增 JWT 登录接口"  → type=feat, scope=auth, desc=新增 JWT 登录接口
  ✓ "fix: 修复分页错误"               → type=fix, scope=None, desc=修复分页错误
  ✓ "docs: 更新 README"              → type=docs, scope=None, desc=更新 README
  ✗ "Merge branch 'main' into dev"   → uncategorized
  ✗ "WIP: 正在开发中"                → uncategorized
  ✗ "update code"                    → uncategorized
```

### 4.2 分类统计输出

```
Commit 分类统计:
┌──────────────┬──────┬──────────┐
│ Type         │ 数量  │ 占比     │
├──────────────┼──────┼──────────┤
│ feat         │ 12   │ 40.0%    │
│ fix          │ 8    │ 26.7%    │
│ refactor     │ 3    │ 10.0%    │
│ docs         │ 2    │ 6.7%     │
│ test         │ 2    │ 6.7%     │
│ chore        │ 1    │ 3.3%     │
│ uncategorized│ 2    │ 6.7%     │
├──────────────┼──────┼──────────┤
│ 合计         │ 30   │ 100%     │
├──────────────┴──────┴──────────┤
│ 格式规范率: 93.3%              │
└────────────────────────────────┘
```

---

## 5. AI Prompt 工程

### 5.1 System Prompt 设计原则

```
1. 角色定义清晰
   - "你是一个专业的软件项目管理分析助手"

2. 输入说明明确
   - 告知 AI 将收到什么格式的数据

3. 输出约束具体
   - 指定输出结构
   - 要求区分事实和推断
   - 要求标注推断依据

4. 防止幻觉
   - "事实描述基于提供的数据，不要编造"
   - "推断和判断需要明确标注「推断」"

5. 可操作性
   - "建议需要具体、可操作"
```

### 5.2 User Message 模板

```
## 项目信息
- 仓库: {owner}/{repo}
- 分支: {branch}
- 分析范围: 最近 {days} 天
- 分析时间: {current_date}

## Commit 统计
- 总计: {total} 条
- 格式规范率: {compliance_rate}%

{by_type_table}

## Commit 列表（最近 {max_commits} 条）
{commit_list}

## 开放 Issue（{issue_count} 个）
{issue_list}

## 开放 PR（{pr_count} 个）
{pr_list}

## 活跃分支（{branch_count} 个）
{branch_list}

---

请基于以上数据生成项目状态摘要。
```

### 5.3 Token 预算

```
Token 分配策略:
  System Prompt:    ~300 tokens
  User Context:     ~3000 tokens (数据部分)
  AI 输出:          ~700 tokens (摘要)
  ─────────────────────────
  总计:             ~4000 tokens

截断策略:
  1. commit 列表超过 50 条 → 保留最近 50 条
  2. issue 列表超过 20 条 → 保留最近更新的 20 条
  3. PR 列表超过 20 条 → 保留最近更新的 20 条
  4. 分支列表超过 15 条 → 保留最近活跃的 15 条
  5. 单条 commit message 超过 200 字符 → 截断
```

---

## 6. 风险识别规则

### 6.1 内置规则（无需 AI 即可判断）

| 规则 | 条件 | 风险级别 |
|---|---|---|
| 长期未关闭 issue | issue 创建超过 30 天仍未关闭 | 中 |
| 大量开放 issue | 开放 issue > 20 个 | 中 |
| PR 长期未合并 | PR 创建超过 7 天未合并 | 中 |
| 大量并行分支 | 活跃分支 > 10 个 | 低 |
| 格式规范率低 | 规范率 < 50% | 低 |
| 无近期活动 | 最近 7 天无 commit | 高 |

### 6.2 AI 推断风险

```
AI 根据上下文推断的风险:
  - 某模块频繁修复 → 可能存在质量问题
  - 某 PR 长期未审查 → 可能存在审查瓶颈
  - 大量 refactor 提交 → 可能正在进行大规模重构
  - feat 占比异常高但 fix 也高 → 可能新功能质量不稳定
```

---

## 7. 异常处理详细设计

### 7.1 异常场景与处理

| 场景 | 处理 | 用户提示 |
|---|---|---|
| GITEA_TOKEN 未设置 | 终止 | "环境变量 GITEA_TOKEN 未设置，请先设置" |
| repo-url 格式错误 | 终止 | "仓库 URL 格式错误，应为 https://..." |
| Gitea 服务器不可达 | 终止 | "无法连接到 Gitea 服务器: {url}" |
| Gitea Token 无效 (401) | 终止 | "GITEA_TOKEN 无效或已过期" |
| Gitea 权限不足 (403) | 终止 | "GITEA_TOKEN 权限不足，需要 read:repository" |
| 仓库不存在 (404) | 终止 | "仓库不存在或无访问权限: {url}" |
| commits 拉取失败 | 降级 | "Commits 数据拉取失败，将跳过 commit 分析" |
| issues 拉取失败 | 降级 | "Issues 数据拉取失败，将跳过 issue 分析" |
| PRs 拉取失败 | 降级 | "PRs 数据拉取失败，将跳过 PR 分析" |
| branches 拉取失败 | 降级 | "Branches 数据拉取失败，将跳过分支分析" |
| AI API 超时 | 降级 | "AI 分析超时，切换为原始数据摘要" |
| AI API 认证失败 | 降级 | "AI API 认证失败，切换为原始数据摘要" |
| AI 响应解析失败 | 降级 | "AI 响应格式异常，切换为原始数据摘要" |
| 全部数据拉取失败 | 终止 | "所有数据源拉取失败，无法生成报告" |

### 7.2 降级输出示例

```
═══════════════════════════════════════════════════════════
          项目数据摘要 - my-team/backend-api - 2026-05-02
                (AI 分析不可用，显示原始数据)
═══════════════════════════════════════════════════════════

⚠ 数据拉取警告:
  - Issues 数据拉取失败: 请求超时

───────────────────────────────────────────────────────────
分析范围: 最近 7 天, main 分支
Commit 总数: 30 | 格式规范率: 93.3%

Commit 分类统计:
  feat:     12 条 (40.0%)
  fix:       8 条 (26.7%)
  refactor:  3 条 (10.0%)
  docs:      2 条 (6.7%)
  test:      2 条 (6.7%)
  chore:     1 条 (3.3%)
  未分类:    2 条 (6.7%)

───────────────────────────────────────────────────────────
近期 Commit 列表:
  a1b2c3d4  feat(auth): 新增 JWT 登录接口 (张三, 05-01)
  e5f6g7h8  fix: 修复用户列表分页错误 (李四, 05-01)
  ...

───────────────────────────────────────────────────────────
开放 PR (3):
  #34 重构用户模块 (张三, 05-01) - 等待审查
  #33 添加日志中间件 (王五, 04-30) - 等待合并
  ...

───────────────────────────────────────────────────────────
分支列表 (5):
  main, feature/user-auth, feature/logging, fix/pagination, dev
```

---

## 8. 性能优化

### 8.1 优化策略

| 策略 | 说明 |
|---|---|
| 并行请求 | 4 个数据源并行拉取，减少总耗时 |
| 连接复用 | 使用 requests.Session 复用 TCP 连接 |
| 分页控制 | 合理设置 per_page (50)，减少请求次数 |
| 数据截断 | 控制 AI 输入上下文大小，避免超 token 限制 |
| 缓存（未来） | 对同一仓库同一天的查询结果做短期缓存 |

### 8.2 预期性能

```
典型场景 (30 commits, 10 issues, 5 PRs, 5 branches):
  - Gitea API 拉取: 2-5 秒 (并行)
  - 数据分类 + 组装: < 0.5 秒
  - AI 分析: 5-15 秒 (取决于模型)
  ─────────────────────────
  总耗时: 10-20 秒
```

---

## 9. 测试方案

### 9.1 单元测试

```
test_gitea_client.py:
  □ test_parse_repo_url_standard
  □ test_parse_repo_url_with_trailing_slash
  □ test_parse_repo_url_with_subpath
  □ test_request_success (mock HTTP)
  □ test_request_retry_on_500 (mock HTTP)
  □ test_request_no_retry_on_401 (mock HTTP)
  □ test_request_timeout_retry (mock HTTP)
  □ test_paginate_single_page (mock HTTP)
  □ test_paginate_multi_page (mock HTTP)
  □ test_fetch_commits (mock HTTP)
  □ test_fetch_issues (mock HTTP)
  □ test_fetch_pull_requests (mock HTTP)
  □ test_fetch_branches (mock HTTP)

test_data_builder.py:
  □ test_classify_commits_standard_format
  □ test_classify_commits_mixed_format
  □ test_classify_commits_all_uncategorized
  □ test_classify_commits_empty_list
  □ test_compute_stats
  □ test_compute_stats_all_uncategorized
  □ test_compute_stats_empty
  □ test_build_analysis_context_length_control
  □ test_build_analysis_context_truncation

test_analyzer.py:
  □ test_analyze_success (mock AI response)
  □ test_analyze_api_error
  □ test_analyze_timeout
  □ test_parse_response_valid
  □ test_parse_response_malformed

test_output.py:
  □ test_format_ai_report
  □ test_build_raw_report
  □ test_build_raw_report_with_errors
  □ test_render_report_to_terminal
  □ test_render_report_to_file
```

### 9.2 集成测试

```
test_integration.py:
  □ test_full_flow_with_mock_gitea (mock 所有 API 响应)
  □ test_full_flow_with_mock_ai (mock AI 响应)
  □ test_full_flow_ai_fallback
  □ test_partial_data_failure (部分 API 失败)
  □ test_all_data_failure
  □ test_no_ai_flag
  □ test_output_to_file
```

### 9.3 E2E 测试

```
test_e2e.py:
  □ 使用真实 Gitea 测试仓库验证完整流程
  □ 验证 commit 分类准确性
  □ 验证 AI 摘要包含必要章节
  □ 验证事实与推断分离
  □ 验证 Markdown 文件输出格式
```

---

## 10. 附录

### 10.1 文件清单

```
repo-analyzer/
  __init__.py
  main.py              (~180 行) 入口 + 参数解析 + 流程编排
  gitea_client.py      (~200 行) Gitea API 封装 + 重试 + 分页
  data_builder.py      (~150 行) commit 分类 + 统计 + 上下文组装
  analyzer.py          (~120 行) AI 调用 + Prompt + 响应解析
  config_loader.py     (~80 行)  配置加载 (与 commit-guide 共享逻辑)
  output.py            (~120 行) 格式化输出 + 降级报告
```

### 10.2 依赖

```
标准库: sys, os, re, json, time, argparse, logging, dataclasses, typing, concurrent.futures
第三方: requests
```

### 10.3 Gitea API 端点参考

| 操作 | 方法 | 路径 |
|---|---|---|
| 获取 commit 列表 | GET | `/api/v1/repos/{owner}/{repo}/commits` |
| 获取 issue 列表 | GET | `/api/v1/repos/{owner}/{repo}/issues` |
| 获取 PR 列表 | GET | `/api/v1/repos/{owner}/{repo}/pulls` |
| 获取分支列表 | GET | `/api/v1/repos/{owner}/{repo}/branches` |

### 10.4 参考文档

- [系统统筹详细设计](./gitea-ai-system-overview-detailed.md)
- [commit-guide 详细设计](./gitea-commit-guide-detailed.md)
- [repo-analyzer 设计方案 (v0.1)](./gitea-repo-analyzer.md)
