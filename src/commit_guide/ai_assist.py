"""AI commit message 生成模块 —— 从 diff 生成标准格式 commit message。"""

from dataclasses import dataclass
from typing import List, Optional

import requests

from .config_loader import get_default_model_config
from .types import COMMIT_TYPE_KEYS, is_valid_commit_message

_SYSTEM_PROMPT = (
    "你是一个 Git commit message 生成助手。"
    "根据提供的 git diff 内容，生成一条符合以下格式的 commit message：\n"
    "\n"
    "  type(scope): 描述\n"
    "\n"
    "规则：\n"
    "1. type 必须是以下之一：{type_list}\n"
    "2. scope 可选，填受影响的模块名（英文），无明确模块时省略\n"
    "3. 描述用中文，简洁说明\"做了什么\"，5-100 字符\n"
    "4. 只输出 commit message 本身，不要解释，不要加引号\n"
    "\n"
    "示例输出：\n"
    "feat(auth): 新增 JWT 登录接口\n"
    "fix: 修复用户列表分页错误"
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
                {
                    "role": "user",
                    "content": "暂存区文件:\n{files}\n\ngit diff:\n{diff}".format(
                        files="\n".join("- {0}".format(f) for f in staged_files),
                        diff=diff,
                    ),
                },
            ],
            "max_tokens": 256,
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
            return GenerateResult(
                success=False,
                reason="AI API error: {0}".format(response.status_code),
            )

        try:
            data = response.json()
            raw = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, ValueError) as exc:
            return GenerateResult(
                success=False, reason="failed to parse AI response: {0}".format(exc)
            )

        if not raw:
            return GenerateResult(
                success=False, reason="AI returned empty response"
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
        # 优先返回第一行，若第一行不以 type 开头则逐行查找
        for line in clean:
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("//"):
                return line
        return clean[0].strip() if clean else None


def check_ai_availability() -> bool:
    return CommitMessageGenerator().is_available()
