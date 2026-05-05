"""Markdown 渲染工具模块 —— 提供列表、风险列表、计数格式化和表格转义等辅助函数。"""

from typing import Dict, List


def bullet_list(items: List[str], empty: str = "无") -> str:
    """将字符串列表渲染为 Markdown 无序列表，列表为空时返回 "- {empty}"。"""
    if not items:
        return "- {0}".format(empty)
    return "\n".join("- {0}".format(item) for item in items)


def risk_list(items: List[Dict], empty: str = "无") -> str:
    """将风险字典列表渲染为 Markdown 无序列表，格式为 [severity] signal: basis。"""
    if not items:
        return "- {0}".format(empty)
    return "\n".join(
        "- [{severity}] {signal}: {basis}".format(
            severity=item.get("severity", "medium"),
            signal=item.get("signal", ""),
            basis=item.get("basis", ""),
        )
        for item in items
    )


def format_counts(counts: Dict[str, int]) -> str:
    """将计数字典格式化为 "key:count, ..." 字符串，按 key 排序，空字典返回 "-"。"""
    if not counts:
        return "-"
    return ", ".join("{0}:{1}".format(key, counts[key]) for key in sorted(counts))


def escape_cell(value: str) -> str:
    """转义 Markdown 表格单元格中的特殊字符（| 和换行符）。"""
    return str(value).replace("|", "\\|").replace("\n", " ")
