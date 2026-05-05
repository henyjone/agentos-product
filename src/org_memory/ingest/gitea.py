"""Gitea 摄入模块 —— 将 Gitea 仓库活动数据（提交、项目文档）转换为 IngestResult。"""

from typing import Dict, List, Optional

from ..domain import Entity, IngestResult, RawEvent, Relationship, Source
from ..ids import entity_id, event_id, relationship_id, source_id
from ..time_utils import utc_now_iso


def build_gitea_ingest_result(activity) -> IngestResult:
    """将一个仓库的 Gitea 活动数据构建为 IngestResult。

    activity 对象需包含 repo（RepoRef）、branch、raw_data 字段。
    raw_data 中的 commits 和 commit_details 会被合并处理；
    project_context 文档会作为独立事件摄入。
    """
    now = utc_now_iso()
    repo_ref = activity.repo
    repo_full_name = repo_ref.full_name or "{0}/{1}".format(repo_ref.owner, repo_ref.repo)
    project_id = entity_id("project", repo_ref.repo)
    repo_id = entity_id("repo", repo_full_name)
    entities: List[Entity] = [
        Entity(id=project_id, type="project", name=repo_ref.repo, aliases=[repo_full_name], created_at=now, updated_at=now),
        Entity(
            id=repo_id,
            type="repo",
            name=repo_full_name,
            aliases=[repo_ref.repo],
            metadata={"default_branch": repo_ref.default_branch, "html_url": repo_ref.html_url},
            created_at=now,
            updated_at=now,
        ),
    ]
    sources: List[Source] = []
    events: List[RawEvent] = []
    # 预建仓库归属关系
    relationships: List[Relationship] = [
        Relationship(
            id=relationship_id(repo_id, "belongs_to", project_id),
            from_entity_id=repo_id,
            to_entity_id=project_id,
            relation_type="belongs_to",
            confidence="high",
            created_at=now,
            updated_at=now,
        )
    ]

    # 摄入项目上下文文档（如 项目背景.md、README.md）
    _append_project_context_documents(
        activity=activity,
        project_id=project_id,
        repo_id=repo_id,
        repo_full_name=repo_full_name,
        entities=entities,
        sources=sources,
        events=events,
        now=now,
    )

    # 按 SHA 前 8 位建立 commit_details 索引，用于快速查找代码变更详情
    raw_commits = activity.raw_data.get("commits", [])
    details_by_sha = _details_by_sha(activity.raw_data.get("commit_details", []))
    for raw_commit in raw_commits:
        sha = _commit_sha(raw_commit)
        if not sha:
            continue
        actor = _commit_actor(raw_commit, sha)
        person_id = entity_id("person", actor)
        commit_id = entity_id("commit", sha)
        detail = details_by_sha.get(sha[:8]) or {}
        message = _commit_message(raw_commit)
        occurred_at = _commit_date(raw_commit) or now
        src_id = source_id("gitea", "commit", "{0}:{1}".format(repo_full_name, sha[:8]))
        entities.extend(
            [
                Entity(id=person_id, type="person", name=actor, created_at=now, updated_at=now),
                Entity(
                    id=commit_id,
                    type="commit",
                    name=sha[:8],
                    metadata={"message": message, "repo": repo_full_name},
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        sources.append(
            Source(
                id=src_id,
                title=message.splitlines()[0] if message else sha[:8],
                source_type="code",
                system="gitea",
                url=_commit_url(repo_ref, sha),
                metadata={"repo": repo_full_name, "sha": sha, "branch": activity.branch},
                created_at=occurred_at,
            )
        )
        events.append(
            RawEvent(
                id=event_id("gitea_commit", "{0}:{1}".format(repo_full_name, sha[:8])),
                event_type="gitea_commit",
                actor_id=person_id,
                project_id=project_id,
                repo_id=repo_id,
                source_id=src_id,
                occurred_at=occurred_at,
                ingested_at=now,
                payload={
                    "repo": repo_full_name,
                    "branch": activity.branch,
                    "sha": sha,
                    "message": message,
                    "files": _changed_files(detail),
                    "additions": _stat_value(detail, "additions"),
                    "deletions": _stat_value(detail, "deletions"),
                    "diff_context": _diff_context(detail),
                    "has_patch": _has_patch(detail),
                },
            )
        )
        relationships.append(
            Relationship(
                id=relationship_id(person_id, "works_on", project_id),
                from_entity_id=person_id,
                to_entity_id=project_id,
                relation_type="works_on",
                source_ids=[src_id],
                confidence="high",
                created_at=now,
                updated_at=now,
            )
        )
    # 去重实体（同一 person 可能在多个 commit 中出现）
    return IngestResult(entities=_dedupe_entities(entities), sources=sources, events=events, relationships=relationships)


def _append_project_context_documents(
    activity,
    project_id: str,
    repo_id: str,
    repo_full_name: str,
    entities: List[Entity],
    sources: List[Source],
    events: List[RawEvent],
    now: str,
) -> None:
    """将 activity.raw_data["project_context"] 中的文档摄入为 project_doc_update 事件。"""
    documents = activity.raw_data.get("project_context", [])
    if not isinstance(documents, list):
        return
    for index, item in enumerate(documents, start=1):
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "project_document_{0}.md".format(index))
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        doc_key = "{0}:{1}:{2}".format(repo_full_name, index, path)
        doc_id = entity_id("document", doc_key)
        src_id = source_id("gitea", "document", doc_key)
        entities.append(
            Entity(
                id=doc_id,
                type="document",
                name=path,
                metadata={"repo": repo_full_name, "path": path, "ref": item.get("ref") or activity.branch},
                created_at=now,
                updated_at=now,
            )
        )
        sources.append(
            Source(
                id=src_id,
                title="{0} - {1}".format(repo_full_name, path),
                source_type="document",
                system="gitea",
                url=_file_url(activity.repo, item.get("ref") or activity.branch, path),
                metadata={"repo": repo_full_name, "path": path, "ref": item.get("ref") or activity.branch},
                created_at=now,
            )
        )
        events.append(
            RawEvent(
                id=event_id("project_doc_update", doc_key),
                event_type="project_doc_update",
                occurred_at=now,
                ingested_at=now,
                actor_id="system:gitea",
                project_id=project_id,
                repo_id=repo_id,
                source_id=src_id,
                payload={
                    "path": path,
                    "title": path,
                    "content": content,
                    "size": item.get("size"),
                    "ref": item.get("ref") or activity.branch,
                },
            )
        )


def _details_by_sha(details: List[Dict]) -> Dict[str, Dict]:
    """将 commit_details 列表转换为以 SHA 前 8 位为 key 的字典，便于快速查找。"""
    return {_commit_sha(item)[:8]: item for item in details if _commit_sha(item)}


def _commit_sha(item: Dict) -> str:
    """从 commit 字典中提取 SHA，兼容 sha 和 id 两种字段名。"""
    return str(item.get("sha") or item.get("id") or "")


def _commit_message(item: Dict) -> str:
    """从 commit 字典中提取提交信息，兼容嵌套 commit.message 和顶层 message 两种结构。"""
    return str((item.get("commit", {}) or {}).get("message") or item.get("message") or "")


def _commit_date(item: Dict) -> str:
    """从 commit 字典中提取提交时间，优先取 commit.author.date，其次取 created_at。"""
    commit_author = (item.get("commit", {}) or {}).get("author", {}) or {}
    return str(commit_author.get("date") or item.get("created_at") or "")


def _commit_actor(item: Dict, sha: str = "") -> str:
    """从 commit 字典中提取操作者标识，按优先级尝试多个字段。"""
    api_author = item.get("author")
    if isinstance(api_author, dict):
        for key in ("login", "username", "full_name", "email", "name"):
            value = api_author.get(key)
            if value:
                return str(value)
    commit_author = (item.get("commit", {}) or {}).get("author", {}) or {}
    value = commit_author.get("email") or commit_author.get("name")
    if value:
        return str(value)
    # 所有字段均为空时，用 SHA 前缀生成匿名标识
    return "anonymous_{0}".format(str(sha or "unknown")[:8])


def _changed_files(detail: Dict) -> List[str]:
    """从 commit detail 中提取变更文件路径列表。"""
    files = detail.get("files") or []
    result: List[str] = []
    if not isinstance(files, list):
        return result
    for item in files:
        if not isinstance(item, dict):
            continue
        path = item.get("filename") or item.get("name") or item.get("path")
        if path:
            result.append(str(path))
    return result


def _stat_value(detail: Dict, key: str) -> int:
    """从 commit detail 的 stats 字段中安全提取整数值。"""
    stats = detail.get("stats") or {}
    try:
        return int(stats.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _has_patch(detail: Dict) -> bool:
    """判断 commit detail 中是否包含 patch/diff 内容。"""
    files = detail.get("files") or []
    return any(isinstance(item, dict) and bool(item.get("patch") or item.get("diff")) for item in files)


def _diff_context(detail: Dict) -> str:
    """从 commit detail 中拼接所有文件的 patch/diff，截断至 4000 字符。"""
    files = detail.get("files") or []
    patches: List[str] = []
    if not isinstance(files, list):
        return ""
    for item in files:
        if not isinstance(item, dict):
            continue
        patch = item.get("patch") or item.get("diff")
        if patch:
            patches.append(str(patch))
    return "\n".join(patches)[:4000]


def _commit_url(repo_ref, sha: str) -> str:
    """构建 commit 的 HTML URL，优先使用 html_url，其次拼接 base_url。"""
    base = repo_ref.html_url.rstrip("/") if repo_ref.html_url else ""
    if not base and repo_ref.base_url:
        base = "{0}/{1}/{2}".format(repo_ref.base_url.rstrip("/"), repo_ref.owner, repo_ref.repo)
    return "{0}/commit/{1}".format(base, sha) if base else ""


def _file_url(repo_ref, ref: str, path: str) -> str:
    """构建文件在指定 ref 下的 HTML URL。"""
    base = repo_ref.html_url.rstrip("/") if repo_ref.html_url else ""
    if not base and repo_ref.base_url:
        base = "{0}/{1}/{2}".format(repo_ref.base_url.rstrip("/"), repo_ref.owner, repo_ref.repo)
    return "{0}/src/branch/{1}/{2}".format(base, ref, path) if base else ""


def _dedupe_entities(entities: List[Entity]) -> List[Entity]:
    """对实体列表去重，保留每个 ID 最后出现的版本（后写覆盖前写）。"""
    result: Dict[str, Entity] = {}
    for entity in entities:
        result[entity.id] = entity
    return list(result.values())
