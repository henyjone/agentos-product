import json
from dataclasses import dataclass
from typing import Dict, List

import requests


class AIAnalysisError(Exception):
    """Raised when AI analysis cannot produce a valid result."""


SYSTEM_PROMPT = """你是一个专业的软件项目管理分析助手。
你会收到 Gitea 仓库数据、commit message 统计、代码变更摘要、patch 摘录和历史日报快照。

要求：
1. 事实必须来自输入数据，不要编造。
2. 推断必须明确说明是 AI 判断。
3. 判断代码工作内容或代码风险时，优先引用 Code Change Evidence，不要只根据 commit message 下结论。
4. 如果代码 diff 没有成功读取，要明确说明证据不足。
5. 如果提供了历史快照，请说明相比上次的变化趋势。
6. 风险要说明依据和严重程度。
7. 建议要具体、可执行。
8. 面向管理者阅读，先讲结论和影响，避免堆砌过多技术细节。

请只输出 JSON，不要输出其他内容。结构：
{
  "summary": "Markdown 格式摘要，尽量简洁，优先说明员工任务和项目状态",
  "facts": ["事实1"],
  "inferences": ["AI 判断1"],
  "risks": [{"signal": "风险", "basis": "依据", "severity": "high|medium|low"}],
  "suggestions": ["建议1"]
}
"""


@dataclass(frozen=True)
class AnalysisResult:
    summary: str
    facts: List[str]
    inferences: List[str]
    risks: List[Dict]
    suggestions: List[str]


class AIAnalyzer:
    def __init__(self, model_config: Dict):
        self.api_base = model_config["api_base"]
        self.api_key = model_config["api_key"]
        self.model = model_config["model"]

    def analyze(self, context: str) -> AnalysisResult:
        raw = self._call_api(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ]
        )
        return self._parse_response(raw)

    def _call_api(self, messages: List[Dict]) -> str:
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
            timeout=60,
        )
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
        text = raw.strip()
        if text.startswith("```"):
            lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
            text = "\n".join(lines).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AIAnalysisError("AI JSON parse failed: {0}".format(exc)) from exc
        return AnalysisResult(
            summary=str(data.get("summary", "")),
            facts=list(data.get("facts", [])),
            inferences=list(data.get("inferences", [])),
            risks=list(data.get("risks", [])),
            suggestions=list(data.get("suggestions", [])),
        )


def run_ai_analysis(context: str, model_config: Dict) -> AnalysisResult:
    return AIAnalyzer(model_config).analyze(context)
