"""AI commit message 生成模块 —— 从 diff 生成标准格式 commit message。"""

from dataclasses import dataclass
from typing import List, Optional

import requests

from .config_loader import get_default_model_config
from .types import COMMIT_TYPE_KEYS, is_valid_commit_message

# 系统提示词：要求 AI 综合所有暂存文件生成符合 Conventional Commit 规范的 message
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
    """AI 生成结果，包含成功标志、message 文本和失败原因。"""

    success: bool
    message: str = ""        # 提取并校验通过的 commit message
    raw_response: str = ""   # AI 原始输出，用于调试
    reason: str = ""         # 失败时的原因描述


class CommitMessageGenerator:
    """从 git diff 生成 commit message 的 AI 客户端封装。

    初始化时尝试加载模型配置；配置不可用时 is_available() 返回 False，
    调用方可据此决定是否降级到手动编辑。
    """

    def __init__(self, model_config: Optional[dict] = None) -> None:
        self.model_config = model_config
        self.available = False
        self._init_ai()

    def _init_ai(self) -> None:
        """尝试加载模型配置，失败时将 available 置为 False 而非抛出异常。"""
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
        """返回 AI 功能是否可用（配置加载成功）。"""
        return self.available

    def generate(self, diff: str, staged_files: List[str]) -> GenerateResult:
        """调用 AI API，从 diff 文本生成 commit message。

        返回 GenerateResult；success=False 时 reason 字段说明失败原因。
        """
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
            "temperature": 0.3,  # 低温度减少随机性，保证格式稳定
        }

        try:
            response = requests.post(
                self.model_config["api_base"],
                headers=headers,
                json=payload,
                timeout=int(self.model_config.get("timeout") or 600),
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
        策略：先找第一行符合规范的 subject，再收集后续正文行；
        找不到规范行时退化为返回第一个非注释行。
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
                # 找到第一行符合规范的 subject 才开始收集
                if is_valid_commit_message(stripped):
                    message_lines.append(stripped)
                    started = True
                continue
            message_lines.append(line.rstrip())
        if message_lines:
            return "\n".join(message_lines).strip()
        # 退化：返回第一个非注释行
        for line in clean:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("//"):
                return stripped
        return None


def check_ai_availability() -> bool:
    """快速检查 AI 功能是否可用（不发起网络请求）。"""
    return CommitMessageGenerator().is_available()
