from pathlib import Path
from typing import Dict, List, Optional

from .analyzer import AnalysisResult
from .code_context import summarize_code_changes
from .data_builder import ClassifiedCommit, compute_stats, identify_builtin_risks


def format_ai_report(
    analysis: AnalysisResult,
    classified: List[ClassifiedCommit],
    raw_data: Dict,
    errors: List[str],
    args,
) -> str:
    stats = compute_stats(classified)
    code_summary = summarize_code_changes(raw_data.get("commit_details", []))
    lines = [
        "# 项目状态摘要",
        "",
        analysis.summary.strip(),
        "",
        "## 数据概览",
        "",
        "- 仓库: {0}".format(getattr(args, "repo_url", "")),
        "- 分支: {0}".format(getattr(args, "branch", "main")),
        "- 分析范围: 最近 {0} 天".format(getattr(args, "days", 7)),
        "- Commit 总数: {0}".format(stats.total),
        "- 格式规范率: {0:.1%}".format(stats.format_compliance_rate),
        "- 已读取代码变更的 Commit: {0}".format(code_summary.commit_count),
        "- 代码变更文件: {0}".format(code_summary.file_count),
        "- 开放 Issue: {0}".format(len(raw_data.get("issues", []))),
        "- 开放 PR: {0}".format(len(raw_data.get("pull_requests", []))),
        "",
        "## 事实",
        "",
        _bullet_list(analysis.facts),
        "",
        "## 推断",
        "",
        _bullet_list(analysis.inferences),
        "",
        "## 风险",
        "",
        _risk_list(analysis.risks),
        "",
        "## 建议",
        "",
        _bullet_list(analysis.suggestions),
        "",
        "## 代码变更摘要",
        "",
        _single_code_summary(code_summary),
    ]
    if errors:
        lines.extend(["", "## 数据拉取警告", "", _bullet_list(errors)])
    return "\n".join(lines).strip() + "\n"


def build_raw_report(
    classified: List[ClassifiedCommit],
    raw_data: Dict,
    errors: List[str],
    args,
) -> str:
    stats = compute_stats(classified)
    risks = identify_builtin_risks(classified, raw_data, getattr(args, "days", 7))
    code_summary = summarize_code_changes(raw_data.get("commit_details", []))
    lines = [
        "# 项目数据摘要",
        "",
        "> AI 分析不可用或已禁用，显示原始数据摘要。",
        "",
        "## 数据概览",
        "",
        "- 仓库: {0}".format(getattr(args, "repo_url", "")),
        "- 分支: {0}".format(getattr(args, "branch", "main")),
        "- 分析范围: 最近 {0} 天".format(getattr(args, "days", 7)),
        "- Commit 总数: {0}".format(stats.total),
        "- 格式规范率: {0:.1%}".format(stats.format_compliance_rate),
        "- 已读取代码变更的 Commit: {0}".format(code_summary.commit_count),
        "- 代码变更文件: {0}".format(code_summary.file_count),
        "- 开放 Issue: {0}".format(len(raw_data.get("issues", []))),
        "- 开放 PR: {0}".format(len(raw_data.get("pull_requests", []))),
        "",
        "## Commit 分类统计",
        "",
        "| Type | 数量 |",
        "|---|---:|",
    ]
    for commit_type, count in stats.by_type.items():
        lines.append("| {0} | {1} |".format(commit_type, count))
    if stats.uncategorized:
        lines.append("| uncategorized | {0} |".format(stats.uncategorized))
    if not stats.by_type and not stats.uncategorized:
        lines.append("| 无 | 0 |")

    lines.extend(
        [
            "",
            "## 近期 Commit",
            "",
            _bullet_list(
                [
                    "{0} {1} ({2}, {3})".format(
                        item.sha,
                        item.full_message,
                        item.author or "unknown",
                        item.date[:10] if item.date else "unknown-date",
                    )
                    for item in classified[: getattr(args, "max_commits", 50)]
                ]
            ),
            "",
            "## 代码变更摘要",
            "",
            _single_code_summary(code_summary),
            "",
            "## 开放 Issue",
            "",
            _bullet_list(_issue_lines(raw_data.get("issues", []))),
            "",
            "## 开放 PR",
            "",
            _bullet_list(_pr_lines(raw_data.get("pull_requests", []))),
            "",
            "## 分支列表",
            "",
            _bullet_list([item.get("name", "unknown") for item in raw_data.get("branches", [])]),
            "",
            "## 内置风险信号",
            "",
            _bullet_list(["[{0}] {1}: {2}".format(r.severity, r.signal, r.basis) for r in risks]),
        ]
    )
    if errors:
        lines.extend(["", "## 数据拉取警告", "", _bullet_list(errors)])
    return "\n".join(lines).strip() + "\n"


def render_report(report: str, output_path: Optional[str]) -> None:
    if output_path:
        Path(output_path).write_text(report, encoding="utf-8")
        print("报告已保存到: {0}".format(output_path))
    else:
        print(report)


def _single_code_summary(summary) -> str:
    return "\n".join(
        [
            "- Commit 明细: {0}".format(summary.commit_count),
            "- 变更文件: {0}".format(summary.file_count),
            "- 增删行: +{0}/-{1}".format(summary.additions, summary.deletions),
            "- 文件类型: {0}".format(_format_counts(summary.by_category)),
            "- 文件样例: {0}".format(", ".join(summary.touched_files) or "-"),
        ]
    )


def _bullet_list(items: List[str]) -> str:
    if not items:
        return "- 无"
    return "\n".join("- {0}".format(item) for item in items)


def _risk_list(items: List[Dict]) -> str:
    if not items:
        return "- 无"
    return "\n".join(
        "- [{severity}] {signal}: {basis}".format(
            severity=item.get("severity", "medium"),
            signal=item.get("signal", ""),
            basis=item.get("basis", ""),
        )
        for item in items
    )


def _issue_lines(items: List[Dict]) -> List[str]:
    return [
        "#{0} {1} ({2})".format(item.get("number", "?"), item.get("title", ""), item.get("created_at", "")[:10])
        for item in items
    ]


def _pr_lines(items: List[Dict]) -> List[str]:
    return [
        "#{0} {1} ({2})".format(item.get("number", "?"), item.get("title", ""), item.get("created_at", "")[:10])
        for item in items
    ]


def _format_counts(counts: Dict[str, int]) -> str:
    if not counts:
        return "-"
    return ", ".join("{0}:{1}".format(key, counts[key]) for key in sorted(counts))
