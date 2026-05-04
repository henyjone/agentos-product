from typing import Dict, List, Tuple

from .gitea_client import GiteaClient, RepoRef, ResourceNotFoundError, fetch_file_content


PROJECT_CONTEXT_FILES = (
    "项目背景.md",
    "项目进度.md",
    "项目目的.md",
    "README.md",
)


def fetch_project_context_documents(
    client: GiteaClient,
    repo: RepoRef,
    branch: str,
    max_chars_per_file: int = 6000,
) -> Tuple[List[Dict], List[str]]:
    documents: List[Dict] = []
    errors: List[str] = []

    for path in PROJECT_CONTEXT_FILES:
        try:
            payload = fetch_file_content(client, repo.owner, repo.repo, path, ref=branch)
        except ResourceNotFoundError:
            continue
        except Exception as exc:
            errors.append("project_context {0}: {1}".format(path, exc))
            continue

        content = (payload.get("decoded_content") or "").strip()
        if not content:
            continue
        documents.append(
            {
                "path": path,
                "ref": branch,
                "size": payload.get("size"),
                "content": _truncate(content, max_chars_per_file),
            }
        )

    return documents, errors


def build_project_context_section(documents: List[Dict], max_chars_per_file: int = 2500) -> str:
    if not documents:
        return "- 未发现项目上下文文档。"

    sections: List[str] = []
    for item in documents:
        content = (item.get("content") or "").strip()
        if not content:
            continue
        sections.extend(
            [
                "### {0}".format(item.get("path", "unknown")),
                "- 版本: {0}".format(item.get("ref", "-") or "-"),
                "```markdown",
                _truncate(content, max_chars_per_file),
                "```",
                "",
            ]
        )
    return "\n".join(sections).strip() or "- 未读取到可用的项目上下文文档。"


def summarize_project_context_documents(documents: List[Dict]) -> str:
    if not documents:
        return "-"
    return ", ".join(item.get("path", "unknown") for item in documents)


def _truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n... 内容已截断"
