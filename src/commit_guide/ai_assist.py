"""AI commit message 生成模块 —— 从 diff 生成标准格式 commit message。"""

from dataclasses import dataclass
from typing import List, Optional

import requests

from .config_loader import get_default_model_config
from .types import COMMIT_TYPE_KEYS, is_valid_commit_message

_SYSTEM_PROMPT = (
    "你是一个资深工程师，负责根据暂存区变更生成 Git commit message。"
    "你会收到 staged 文件清单、stat、numstat 和按文件截断后的 diff 片段。"
    "必须综合所有暂存文件，不要只根据第一个文件或最大文档判断。\n"
    "\n"
    "输出格式：\n"
    "第一行必须是一条符合 Conventional Commit 的 subject：\n"
    "  type(scope): 描述\n"
    "空一行后可以写 2-5 条正文要点，每条以 '- ' 开头。\n"
    "\n"
    "规则：\n"
    "1. type 必须是以下之一：{type_list}\n"
    "2. scope 可选，填受影响的模块名（英文），无明确模块时省略\n"
    "3. subject 描述用中文，简洁说明主要工程变更，5-100 字符\n"
    "4. 如果同时包含代码和文档，优先以代码变更决定 type/scope，正文再补充文档\n"
    "5. 正文要点覆盖主要代码变更、文档/测试变更，不要编造 diff 中没有的信息\n"
    "6. 只输出 commit message 本身，不要解释，不要加引号\n"
    "\n"
    "示例输出：\n"
    "feat(commit-guide): 支持基于暂存区 diff 生成提交说明\n"
    "\n"
    "- 新增 AI 分析暂存区 diff 的提交信息生成流程\n"
    "- 补充配置读取、Git 状态检测和手动编辑降级逻辑"
).format(type_list=" / ".join(COMMIT_TYPE_KEYS))


@dataclass(frozen=True)
class GenerateResult:
    success: bool
    message: str = ""
    raw_response: str = ""
    reason: str = ""


class CommitMessageGenerator:
    """从 git diff 生成 commit message。"""

    def __init__(self, model_config: Optional[dict] = None) -> None:
        self.model_config = model_config
        self.available = False
        self._init_ai()

    def _init_ai(self) -> None:
        if self.model_config is not None:
            self.available = True
            return
        try:
            self.model_config = get_default_model_config()
            self.available = True
        except Exception:
            self.model_config = None
            self.available = False

    def is_available(self) -> bool:
        return self.available

    def generate(self, diff: str, staged_files: List[str]) -> GenerateResult:
        if not self.available or not self.model_config:
            return GenerateResult(
                success=False, reason="AI model config unavailable"
            )
        if not diff.strip():
            return GenerateResult(
                success=False, reason="diff is empty, nothing to analyze"
            )

        headers = {
            "Authorization": "Bearer {0}".format(self.model_config["api_key"]),
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model_config["model"],
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": diff},
            ],
            "max_tokens": 1024,
            "temperature": 0.3,
        }

        try:
            response = requests.post(
                self.model_config["api_base"],
                headers=headers,
                json=payload,
                timeout=30,
            )
        except Exception as exc:
            return GenerateResult(success=False, reason=str(exc))

        if response.status_code != 200:
            detail = response.text[:500] if response.text else "no body"
            return GenerateResult(
                success=False,
                reason="AI API error {0}: {1}".format(response.status_code, detail),
            )

        try:
            data = response.json()
        except ValueError as exc:
            return GenerateResult(
                success=False,
                reason="failed to parse AI response JSON: {0}".format(exc),
            )

        try:
            message_obj = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            import json as _json
            return GenerateResult(
                success=False,
                reason="unexpected AI response structure: {0} | body={1}".format(
                    exc,
                    _json.dumps(data, ensure_ascii=False)[:500],
                ),
            )

        raw = (message_obj.get("content") or "").strip()
        # DeepSeek 等推理模型可能把结果放在 reasoning_content 而非 content
        if not raw:
            reasoning = (message_obj.get("reasoning_content") or "").strip()
            if reasoning:
                raw = reasoning
            else:
                import json as _json
                return GenerateResult(
                    success=False,
                    reason="AI returned empty content | message={0}".format(
                        _json.dumps(message_obj, ensure_ascii=False)[:500],
                    ),
                )

        message = self._extract_message(raw)
        if message and is_valid_commit_message(message):
            return GenerateResult(
                success=True, message=message, raw_response=raw
            )
        return GenerateResult(
            success=False,
            message=message or "",
            raw_response=raw,
            reason="AI 输出的格式不符合规范，请手动编辑",
        )

    @staticmethod
    def _extract_message(raw: str) -> Optional[str]:
        """从 AI 原始输出中提取 commit message。

        处理 AI 可能包裹 ``` 代码块或添加多余说明的情况。
        """
        lines = raw.strip().split("\n")
        # 去掉 ``` 包裹行
        clean = [l for l in lines if not l.startswith("```")]
        if not clean:
            return None
        message_lines = []
        started = False
        for line in clean:
            stripped = line.strip()
            if not stripped and not started:
                continue
            if not started:
                if is_valid_commit_message(stripped):
                    message_lines.append(stripped)
                    started = True
                continue
            message_lines.append(line.rstrip())
        if message_lines:
            return "\n".join(message_lines).strip()
        for line in clean:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("//"):
                return stripped
        return None


def check_ai_availability() -> bool:
    return CommitMessageGenerator().is_available()
