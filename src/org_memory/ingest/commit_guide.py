"""commit_guide 摄入模块 —— 将一次 commit-guide 提交操作转换为 IngestResult。"""

from typing import List, Optional

from ..domain import Entity, IngestResult, RawEvent, Source
from ..ids import entity_id, event_id, source_id
from ..time_utils import utc_now_iso


def build_commit_guide_ingest_result(
    repo_name: str,
    branch: str,
    staged_files: List[str],
    diff_context: str,
    commit_message: str,
    commit_sha: str,
    actor: str,
    repo_full_name: Optional[str] = None,
    push_remote: Optional[str] = None,
) -> IngestResult:
    """将 commit-guide 的一次提交操作构建为 IngestResult。

    生成的实体包括：操作者（person）、项目（project）、仓库（repo）、提交（commit）。
    生成一个 commit_guide_submit 类型的 RawEvent，payload 包含完整的 diff 上下文。
    """
    now = utc_now_iso()
    # repo_full_name 优先用于跨系统关联（如 owner/repo 格式），否则退化为 repo_name
    repo_key = repo_full_name or repo_name
    person_id = entity_id("person", actor)
    project_id = entity_id("project", repo_name)
    repo_id = entity_id("repo", repo_key)
    commit_entity_id = entity_id("commit", commit_sha)
    src_id = source_id("commit_guide", "code", commit_sha)
    event_key = "{0}:{1}".format(repo_key, commit_sha)

    entities = [
        Entity(id=person_id, type="person", name=actor, created_at=now, updated_at=now),
        Entity(id=project_id, type="project", name=repo_name, owner_id=person_id, created_at=now, updated_at=now),
        Entity(
            id=repo_id,
            type="repo",
            name=repo_key,
            aliases=[repo_name],
            owner_id=person_id,
            metadata={"branch": branch},
            created_at=now,
            updated_at=now,
        ),
        Entity(
            id=commit_entity_id,
            type="commit",
            name=commit_sha[:8],  # 短 SHA 作为显示名称
            metadata={"message": commit_message, "branch": branch},
            created_at=now,
            updated_at=now,
        ),
    ]
    source = Source(
        id=src_id,
        title=commit_message.splitlines()[0] if commit_message else commit_sha,
        source_type="code",
        system="commit_guide",
        metadata={"repo": repo_key, "sha": commit_sha, "branch": branch},
        created_at=now,
    )
    event = RawEvent(
        id=event_id("commit_guide_submit", event_key),
        event_type="commit_guide_submit",
        actor_id=person_id,
        project_id=project_id,
        repo_id=repo_id,
        source_id=src_id,
        occurred_at=now,
        ingested_at=now,
        payload={
            "repo": repo_key,
            "branch": branch,
            "staged_files": staged_files,
            "diff_context": diff_context,
            "commit_message": commit_message,
            "message": commit_message,  # 冗余字段，兼容 fact_extractor 的 message 键
            "sha": commit_sha,
            "push_remote": push_remote,
            "has_patch": bool(diff_context.strip()),
        },
    )
    return IngestResult(entities=entities, sources=[source], events=[event])
