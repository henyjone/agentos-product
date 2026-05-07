import json
import os
from dataclasses import dataclass
from typing import Dict, List

import requests


class AIAnalysisError(Exception):
    """Raised when AI analysis cannot produce a valid result."""


DEFAULT_AI_TIMEOUT_SECONDS = 300
AI_TIMEOUT_ENV = "REPO_ANALYZER_AI_TIMEOUT_SECONDS"


SYSTEM_PROMPT = """你是一个专业的软件项目管理分析助手。
你会收到 Gitea 仓库数据、项目上下文文档、组织记忆上下文、commit message 统计、代码变更摘要、patch 摘录和历史日报快照。

要求：
1. 事实必须来自输入数据，不要编造。
2. 推断必须明确说明是 AI 判断。
3. 判断代码工作内容或代码风险时，优先引用 Code Change Evidence，不要只根据 commit message 下结论。
4. 可以用项目上下文文档理解项目目标、阶段和模块边界，但近期完成工作必须来自 Git 数据。
5. 可以用组织记忆理解历史连续性、人员背景和项目归属，但不要把组织记忆中的历史事实当成本次近期完成工作。
6. 如果代码 diff 没有成功读取，要明确说明证据不足。
7. 如果提供了历史快照或组织记忆，请说明相比上次或历史事实的变化趋势。
8. 风险要说明依据和严重程度。
9. 建议要具体、可执行。
10. 面向管理者阅读，先讲结论和影响，避免堆砌过多技术细节。

请只输出 JSON，不要输出其他内容。结构：
{
  "summary": "Markdown 格式摘要，尽量简洁，优先说明员工任务和项目状态",
  "facts": ["事实1"],
  "inferences": ["AI 判断1"],
  "risks": [{"signal": "风险", "basis": "依据", "severity": "high|medium|low"}],
  "suggestions": ["建议1"]
}
"""


WORK_SUMMARY_PROMPT = """你是一个管理者日报助手。
你会收到 Gitea 仓库提交、代码变更、员工聚合、历史数据、组织记忆上下文和项目上下文文档。

目标：
只总结“谁完成了什么工作”。不要输出项目表、风险、建议、统计口径、相关项目列表。

要求：
1. 事实必须来自输入数据，不要编造。
2. 每个员工输出 1-5 条完成工作。
3. 工作事项要面向管理者阅读，用自然语言概括，不要直接复制 commit 前缀。
4. 可以用项目上下文文档理解项目背景和模块含义，但不要把文档内容当成近期完成工作。
5. 可以用组织记忆识别历史连续性和重复工作，但不要把历史组织记忆当成今天完成的工作。
6. 如果证据主要来自 commit message，可以归纳但不要夸大为已验收完成。
7. 输出必须是 JSON，不要输出其他内容。

结构：
{
  "employees": [
    {
      "name": "员工标识",
      "work_items": ["完成工作1", "完成工作2"]
    }
  ]
}
"""


DETAIL_WORKLOG_PROMPT = """你是一个代码工作日志分析助手。
你会收到指定仓库、员工、路径或 commit 范围内的 Git 扫描证据，包括项目上下文文档、组织记忆上下文、commit 列表、diff 摘要、patch 摘录和文件内容快照。

目标：
生成一份详细工作日志，帮助管理者或后续 Agent 理解这段 Git 变更到底做了什么。

要求：
1. 事实必须来自输入数据，不要编造。
2. “完成工作”要按功能/模块归纳，不要逐条复制 commit message。
3. 可以用项目上下文文档解释变更属于哪个项目目标或模块，但近期完成工作必须来自 Git 证据。
4. 可以用组织记忆解释历史连续性，但不要把历史事实当成本次变更事实。
5. “实现判断”必须引用 diff、变更文件或文件内容快照中的证据。
6. 如果证据不足，要明确写“证据不足”，不要猜测。
7. 风险和后续事项要具体、可操作。
8. 输出必须是 JSON，不要输出其他内容。

结构：
{
  "summary": "Markdown 格式的详细工作日志摘要",
  "facts": ["完成工作或事实1"],
  "inferences": ["基于代码证据的实现判断1"],
  "risks": [{"signal": "风险", "basis": "依据", "severity": "high|medium|low"}],
  "suggestions": ["后续事项1"]
}
"""


@dataclass(frozen=True)
class AnalysisResult:
    summary: str
    facts: List[str]
    inferences: List[str]
    risks: List[Dict]
    suggestions: List[str]


@dataclass(frozen=True)
class EmployeeWorkSummary:
    name: str
    work_items: List[str]


@dataclass(frozen=True)
class WorkSummaryResult:
    employees: List[EmployeeWorkSummary]


class AIAnalyzer:
    def __init__(self, model_config: Dict):
        self.api_base = model_config["api_base"]
        self.api_key = model_config["api_key"]
        self.model = model_config["model"]
        self.timeout = _resolve_timeout(model_config)

    def analyze(self, context: str) -> AnalysisResult:
        raw = self._call_api(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ]
        )
        return self._parse_response(raw)

    def analyze_work_summary(self, context: str) -> WorkSummaryResult:
        raw = self._call_api(
            [
                {"role": "system", "content": WORK_SUMMARY_PROMPT},
                {"role": "user", "content": context},
            ]
        )
        return self._parse_work_summary(raw)

    def analyze_detail_worklog(self, context: str) -> AnalysisResult:
        raw = self._call_api(
            [
                {"role": "system", "content": DETAIL_WORKLOG_PROMPT},
                {"role": "user", "content": context},
            ]
        )
        return self._parse_response(raw)

    def _call_api(self, messages: List[Dict]) -> str:
        try:
            response = requests.post(
                self.api_base,
                headers={
                    "Authorization": "Bearer {0}".format(self.api_key),
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": 4096,
                    "temperature": 0.4,
                },
                timeout=self.timeout,
            )
        except requests.Timeout as exc:
            raise AIAnalysisError("AI API request timed out after {0} seconds".format(self.timeout)) from exc
        except requests.RequestException as exc:
            raise AIAnalysisError("AI API request failed: {0}".format(exc)) from exc
        if response.status_code != 200:
            raise AIAnalysisError(
                "AI API returned error: {0} {1}".format(response.status_code, response.text[:200])
            )
        try:
            data = response.json()
            message = data["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AIAnalysisError("AI response shape is invalid: {0}".format(exc)) from exc
        content = (message.get("content") or "").strip()
        if not content:
            content = (message.get("reasoning_content") or "").strip()
        if not content:
            raise AIAnalysisError("AI response is empty")
        return content

    def _parse_response(self, raw: str) -> AnalysisResult:
        data = self._parse_json(raw)
        return AnalysisResult(
            summary=str(data.get("summary", "")),
            facts=list(data.get("facts", [])),
            inferences=list(data.get("inferences", [])),
            risks=list(data.get("risks", [])),
            suggestions=list(data.get("suggestions", [])),
        )

    def _parse_work_summary(self, raw: str) -> WorkSummaryResult:
        data = self._parse_json(raw)
        employees: List[EmployeeWorkSummary] = []
        for item in data.get("employees", []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            work_items = [str(value).strip() for value in item.get("work_items", []) if str(value).strip()]
            if name and work_items:
                employees.append(EmployeeWorkSummary(name=name, work_items=work_items))
        if not employees:
            raise AIAnalysisError("AI work summary is empty")
        return WorkSummaryResult(employees=employees)

    def _parse_json(self, raw: str) -> Dict:
        text = raw.strip()
        if text.startswith("```"):
            lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
            text = "\n".join(lines).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AIAnalysisError("AI JSON parse failed: {0}".format(exc)) from exc
        if not isinstance(data, dict):
            raise AIAnalysisError("AI JSON root must be an object")
        return data


def run_ai_analysis(context: str, model_config: Dict) -> AnalysisResult:
    return AIAnalyzer(model_config).analyze(context)


def run_work_summary_analysis(context: str, model_config: Dict) -> WorkSummaryResult:
    return AIAnalyzer(model_config).analyze_work_summary(context)


def run_detail_worklog_analysis(context: str, model_config: Dict) -> AnalysisResult:
    return AIAnalyzer(model_config).analyze_detail_worklog(context)


def _resolve_timeout(model_config: Dict) -> int:
    value = model_config.get("timeout") or model_config.get("timeout_seconds") or os.environ.get(AI_TIMEOUT_ENV)
    if value is None:
        return DEFAULT_AI_TIMEOUT_SECONDS
    try:
        timeout = int(value)
    except (TypeError, ValueError):
        return DEFAULT_AI_TIMEOUT_SECONDS
    return timeout if timeout > 0 else DEFAULT_AI_TIMEOUT_SECONDS
