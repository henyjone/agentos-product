"""组织记忆上下文模块 —— 为 repo_analyzer 读取 org_memory 并格式化为 AI/report 上下文。"""

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from org_memory.domain import Fact, MemoryQuery
from org_memory.ids import entity_id
from org_memory.store import LocalSQLiteMemoryStore

from .gitea_client import RepoRef


DEFAULT_MEMORY_LIMIT = 50
DEFAULT_MEMORY_DAYS = 30
DEFAULT_MEMORY_SHOW_LIMIT = 8
DEFAULT_MEMORY_ROLE = "manager"
DEFAULT_MEMORY_USER_ID = "system:repo_analyzer"


def resolve_memory_db_path(args) -> Path:
    """解析 org_memory SQLite 路径，默认落在项目 data 目录下。"""
    if getattr(args, "memory_db", None):
        return Path(args.memory_db).expanduser()
    return Path(__file__).resolve().parents[2] / "data" / "org_memory.sqlite"


def load_memory_context_for_repos(
    repos: Iterable[RepoRef],
    args,
    person_labels: Optional[Iterable[str]] = None,
) -> Dict:
    """按仓库和可选人员标识读取组织记忆事实，返回可序列化快照字典。

    读取失败不会中断报告生成；错误会放入 warnings，供报告和日志展示。
    """
    if not getattr(args, "use_memory", False):
        return {"enabled": False, "facts": [], "warnings": []}

    db_path = resolve_memory_db_path(args)
    snapshot = {
        "enabled": True,
        "db_path": str(db_path),
        "facts": [],
        "warnings": [],
        "query": {
            "project_ids": _project_ids(repos),
            "person_ids": _person_ids(person_labels or []),
            "memory_days": getattr(args, "memory_days", DEFAULT_MEMORY_DAYS),
            "memory_limit": getattr(args, "memory_limit", DEFAULT_MEMORY_LIMIT),
            "memory_show_limit": getattr(args, "memory_show_limit", DEFAULT_MEMORY_SHOW_LIMIT),
        },
    }
    if not db_path.exists():
        snapshot["warnings"].append("org_memory 数据库不存在：{0}".format(db_path))
        return snapshot

    try:
        store = LocalSQLiteMemoryStore(str(db_path))
        query = MemoryQuery(
            user_id=getattr(args, "memory_user_id", DEFAULT_MEMORY_USER_ID) or DEFAULT_MEMORY_USER_ID,
            role=getattr(args, "memory_role", DEFAULT_MEMORY_ROLE) or DEFAULT_MEMORY_ROLE,
            project_ids=snapshot["query"]["project_ids"],
            person_ids=snapshot["query"]["person_ids"],
            time_from=_memory_time_from(getattr(args, "memory_days", DEFAULT_MEMORY_DAYS)),
            limit=max(1, int(getattr(args, "memory_limit", DEFAULT_MEMORY_LIMIT))),
            reason="repo_analyzer --use-memory",
        )
        facts = store.search_facts(query)
        snapshot["facts"] = [_fact_to_dict(store, fact) for fact in facts]
        store.audit(
            action="repo_analyzer_read_memory",
            target_type="memory_context",
            target_id=",".join(snapshot["query"]["project_ids"]) or "all",
            actor_id=query.user_id,
            reason="use-memory CLI option",
        )
    except Exception as exc:
        snapshot["warnings"].append("org_memory 读取失败：{0}".format(exc))
    return snapshot


def build_memory_prompt_section(snapshot: Optional[Dict], max_items: Optional[int] = None) -> str:
    """将组织记忆快照格式化为 AI prompt 上下文。"""
    if not snapshot or not snapshot.get("enabled"):
        return "- Organization memory was not enabled."
    lines = [
        "- 说明：以下内容来自历史组织记忆，只能作为项目连续性、人员上下文和趋势判断依据；近期完成工作仍必须以本次 Git 扫描证据为准。",
        "- 数据库: {0}".format(snapshot.get("db_path", "-")),
    ]
    warnings = snapshot.get("warnings") or []
    if warnings:
        lines.append("- 读取警告: {0}".format("；".join(str(item) for item in warnings)))

    facts = snapshot.get("facts") or []
    if not facts:
        lines.append("- 未读取到匹配的历史事实。")
        return "\n".join(lines)

    limit = _section_limit(snapshot, max_items)
    lines.append("- 匹配事实数: {0}".format(len(facts)))
    for item in facts[:limit]:
        lines.append(
            "- [{confidence}] {date} {content} | subject={subject} project={project} sources={sources}".format(
                confidence=item.get("confidence", "medium"),
                date=item.get("valid_from") or item.get("updated_at", "")[:10] or "-",
                content=item.get("content", ""),
                subject=item.get("subject_entity_id") or "-",
                project=item.get("project_id") or "-",
                sources=", ".join(item.get("source_titles") or item.get("source_ids") or []) or "-",
            )
        )
    if len(facts) > limit:
        lines.append("- 另有 {0} 条历史事实未展开。".format(len(facts) - limit))
    return "\n".join(lines)


def build_memory_report_section(snapshot: Optional[Dict], max_items: Optional[int] = None) -> str:
    """将组织记忆快照格式化为报告中的简短区块。未启用时返回空字符串。"""
    if not snapshot or not snapshot.get("enabled"):
        return ""
    lines = [
        "## 组织记忆参考",
        "",
        "> 仅作为历史上下文，本次完成工作仍以当前 Git 扫描结果为准。",
        "",
    ]
    warnings = snapshot.get("warnings") or []
    if warnings:
        lines.extend(["- 读取警告: {0}".format("；".join(str(item) for item in warnings)), ""])

    facts = snapshot.get("facts") or []
    if not facts:
        lines.append("- 未读取到匹配的历史事实。")
        return "\n".join(lines).strip()

    limit = _section_limit(snapshot, max_items)
    for item in facts[:limit]:
        lines.append(
            "- [{confidence}] {date} {content}".format(
                confidence=item.get("confidence", "medium"),
                date=item.get("valid_from") or item.get("updated_at", "")[:10] or "-",
                content=item.get("content", ""),
            )
        )
    if len(facts) > limit:
        lines.append("- 另有 {0} 条历史事实未展开。".format(len(facts) - limit))
    return "\n".join(lines).strip()


def _fact_to_dict(store: LocalSQLiteMemoryStore, fact: Fact) -> Dict:
    data = asdict(fact)
    source_titles: List[str] = []
    for source_id in fact.source_ids[:3]:
        source = store.get_source(source_id)
        if source:
            source_titles.append(source.title or source.id)
        else:
            source_titles.append(source_id)
    data["source_titles"] = source_titles
    return data


def _project_ids(repos: Iterable[RepoRef]) -> List[str]:
    ids = []
    for repo in repos:
        if repo.repo:
            ids.append(entity_id("project", repo.repo))
    return sorted(set(ids))


def _person_ids(labels: Iterable[str]) -> List[str]:
    result = []
    for label in labels:
        value = str(label or "").strip()
        if value:
            result.append(entity_id("person", value))
    return sorted(set(result))


def _memory_time_from(memory_days: int) -> Optional[str]:
    try:
        days = int(memory_days)
    except (TypeError, ValueError):
        days = DEFAULT_MEMORY_DAYS
    if days <= 0:
        return None
    return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()


def _section_limit(snapshot: Dict, max_items: Optional[int]) -> int:
    if max_items is not None:
        return max(0, int(max_items))
    query = snapshot.get("query") or {}
    return max(0, int(query.get("memory_show_limit") or DEFAULT_MEMORY_SHOW_LIMIT))
