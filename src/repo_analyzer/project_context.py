"""项目上下文模块 —— 从 Gitea 仓库获取项目文档，并格式化为 AI 分析上下文。"""

from typing import Dict, List, Tuple

from .gitea_client import GiteaClient, RepoRef, ResourceNotFoundError, fetch_file_content


# 默认尝试获取的项目文档文件名列表，按优先级排序
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
    """从仓库获取项目上下文文档，返回 (documents, errors)。

    文件不存在时静默跳过（ResourceNotFoundError），其他错误记录到 errors 列表。
    每个文档字典包含 path、ref、size、content 字段。
    """
    documents: List[Dict] = []
    errors: List[str] = []

    for path in PROJECT_CONTEXT_FILES:
        try:
            payload = fetch_file_content(client, repo.owner, repo.repo, path, ref=branch)
        except ResourceNotFoundError:
            continue  # 文件不存在是正常情况，不记录错误
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
    """将项目文档列表格式化为 Markdown 代码块，供 AI 分析上下文使用。"""
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
    """返回文档路径的逗号分隔摘要，用于日志和报告中的简短描述。"""
    if not documents:
        return "-"
    return ", ".join(item.get("path", "unknown") for item in documents)


def _truncate(text: str, max_chars: int) -> str:
    """截断文本到指定字符数，超出时追加中文截断提示。"""
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n... 内容已截断"
