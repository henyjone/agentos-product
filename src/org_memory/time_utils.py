"""时间工具模块 —— 提供统一的 UTC 时间戳生成函数。"""

from datetime import datetime, timezone


def utc_now_iso() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串，精度到秒（去除微秒）。

    示例：'2026-05-05T08:30:00+00:00'
    """
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
