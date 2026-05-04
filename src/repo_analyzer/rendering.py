from typing import Dict, List


def bullet_list(items: List[str], empty: str = "无") -> str:
    if not items:
        return "- {0}".format(empty)
    return "\n".join("- {0}".format(item) for item in items)


def risk_list(items: List[Dict], empty: str = "无") -> str:
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
    if not counts:
        return "-"
    return ", ".join("{0}:{1}".format(key, counts[key]) for key in sorted(counts))


def escape_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
