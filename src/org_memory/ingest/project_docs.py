"""项目文档摄入模块 —— 将本地项目文档文件（如 项目背景.md）摄入为组织记忆事件。"""

from pathlib import Path
from typing import Iterable, List, Optional

from ..domain import Entity, IngestResult, RawEvent, Source
from ..ids import entity_id, event_id, source_id
from ..time_utils import utc_now_iso


# 默认扫描的项目文档文件名列表，按优先级排序
PROJECT_CONTEXT_FILES = (
    "项目背景.md",
    "项目进度.md",
    "项目目的.md",
    "README.md",
)


def build_project_docs_ingest_result(
    project_root: str,
    project_name: str,
    actor: str = "system:project_docs",
    project_id: Optional[str] = None,
    filenames: Iterable[str] = PROJECT_CONTEXT_FILES,
    max_chars_per_file: int = 12000,
) -> IngestResult:
    """扫描项目根目录下的文档文件，将其内容构建为 IngestResult。

    每个存在且非空的文档文件会生成一个 document 实体、一个 Source 和一个
    project_doc_update 事件。文件内容超过 max_chars_per_file 时截断。
    """
    root = Path(project_root)
    now = utc_now_iso()
    resolved_project_id = project_id or entity_id("project", project_name)
    entities: List[Entity] = [
        Entity(
            id=resolved_project_id,
            type="project",
            name=project_name,
            created_at=now,
            updated_at=now,
        )
    ]
    sources: List[Source] = []
    events: List[RawEvent] = []

    for index, filename in enumerate(filenames, start=1):
        path = root / filename
        if not path.is_file():
            continue
        content = _read_text(path).strip()
        if not content:
            continue
        content = content[:max(0, max_chars_per_file)]
        doc_id = entity_id("document", "{0}:{1}:{2}".format(project_name, index, filename))
        src_id = source_id("project_docs", "document", "{0}:{1}:{2}".format(project_name, index, filename))
        entities.append(
            Entity(
                id=doc_id,
                type="document",
                name=filename,
                metadata={"path": str(path), "project": project_name},
                created_at=now,
                updated_at=now,
            )
        )
        sources.append(
            Source(
                id=src_id,
                title="{0} - {1}".format(project_name, filename),
                source_type="document",
                system="project_docs",
                url=str(path),
                metadata={"path": str(path), "project": project_name},
                created_at=now,
            )
        )
        events.append(
            RawEvent(
                id=event_id("project_doc_update", "{0}:{1}:{2}".format(project_name, index, filename)),
                event_type="project_doc_update",
                occurred_at=now,
                ingested_at=now,
                actor_id=actor,
                project_id=resolved_project_id,
                source_id=src_id,
                payload={
                    "path": str(path),
                    "title": filename,
                    "content": content,
                    "size": path.stat().st_size,
                },
            )
        )

    return IngestResult(entities=entities, sources=sources, events=events)


def _read_text(path: Path) -> str:
    """读取文件文本，优先 UTF-8，失败时尝试 UTF-8-SIG（带 BOM 的 Windows 文件）。"""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8-sig")
