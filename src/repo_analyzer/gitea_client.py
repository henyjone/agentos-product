import time
import base64
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, urlparse

import requests


class GiteaError(Exception):
    """Base exception for Gitea API errors."""


class AuthError(GiteaError):
    """Authentication or authorization failure."""


class ResourceNotFoundError(GiteaError):
    """Requested resource does not exist or is inaccessible."""


class APIError(GiteaError):
    """Non-retryable API error."""


class NetworkError(GiteaError):
    """Network-level error after retries."""


@dataclass(frozen=True)
class RepoRef:
    base_url: str
    owner: str
    repo: str
    full_name: str = ""
    html_url: str = ""
    default_branch: str = ""


def parse_repo_url(url: str) -> RepoRef:
    parsed = urlparse(url.rstrip("/"))
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("repo-url 必须是 http/https URL")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise ValueError("repo-url 必须包含 owner/repo")

    owner = parts[-2]
    repo = parts[-1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    base_path = "/".join(parts[:-2])
    base_url = "{0}://{1}".format(parsed.scheme, parsed.netloc)
    if base_path:
        base_url = "{0}/{1}".format(base_url, base_path)
    return RepoRef(
        base_url=base_url,
        owner=owner,
        repo=repo,
        full_name="{0}/{1}".format(owner, repo),
        html_url=url.rstrip("/"),
        default_branch="",
    )


def repo_ref_from_api(base_url: str, item: Dict) -> RepoRef:
    owner_data = item.get("owner", {}) or {}
    full_name = item.get("full_name") or ""
    owner = owner_data.get("login") or owner_data.get("username") or ""
    repo = item.get("name") or ""
    if (not owner or not repo) and "/" in full_name:
        owner, repo = full_name.split("/", 1)
    if not owner or not repo:
        raise ValueError("repository item missing owner/name")
    return RepoRef(
        base_url=base_url.rstrip("/"),
        owner=owner,
        repo=repo,
        full_name=full_name or "{0}/{1}".format(owner, repo),
        html_url=item.get("html_url") or item.get("clone_url") or "",
        default_branch=item.get("default_branch") or "",
    )


class GiteaClient:
    """Read-only Gitea API client."""

    def __init__(self, base_url: str, token: str, session: Optional[requests.Session] = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Authorization": "token {0}".format(token),
                "Accept": "application/json",
            }
        )
        self.max_retries = 3
        self.timeout = 30

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
    ):
        url = "{0}/api/v1{1}".format(self.base_url, path)
        for attempt in range(self.max_retries):
            try:
                response = self.session.request(
                    method,
                    url,
                    params=params,
                    timeout=self.timeout,
                )
            except requests.Timeout as exc:
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise NetworkError("请求超时") from exc
            except requests.ConnectionError as exc:
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise NetworkError("无法连接到 Gitea 服务器") from exc

            if response.status_code == 200:
                return response.json()
            if response.status_code == 401:
                raise AuthError("GITEA_TOKEN 无效或已过期")
            if response.status_code == 403:
                raise AuthError("GITEA_TOKEN 权限不足")
            if response.status_code == 404:
                raise ResourceNotFoundError("资源不存在: {0}".format(path))
            if response.status_code >= 500 and attempt < self.max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            if response.status_code >= 500:
                raise APIError("服务器错误: {0}".format(response.status_code))
            raise APIError(
                "API 错误: {0} {1}".format(response.status_code, response.text[:200])
            )
        raise NetworkError("请求失败")

    def _paginate(self, path: str, params: Optional[Dict] = None) -> List[Dict]:
        items: List[Dict] = []
        page = 1
        per_page = 50
        while True:
            paged_params = dict(params or {})
            paged_params["page"] = page
            paged_params["limit"] = per_page
            page_items = self._request("GET", path, paged_params)
            if not page_items:
                break
            if isinstance(page_items, list):
                items.extend(page_items)
                if len(page_items) < per_page:
                    break
            else:
                items.append(page_items)
                break
            page += 1
        return items


def fetch_commits(
    client: GiteaClient,
    owner: str,
    repo: str,
    branch: str,
    since: str,
    max_count: int = 50,
    include_code: bool = False,
) -> List[Dict]:
    path = "/repos/{0}/{1}/commits".format(owner, repo)
    params = {"sha": branch, "since": since, "limit": max_count}
    if include_code:
        params["stat"] = True
        params["files"] = True
    commits = client._request("GET", path, params)
    if isinstance(commits, list):
        return commits[:max_count]
    return []


def fetch_issues(
    client: GiteaClient,
    owner: str,
    repo: str,
    state: str = "open",
) -> List[Dict]:
    path = "/repos/{0}/{1}/issues".format(owner, repo)
    issues = client._paginate(path, {"state": state})
    return [
        item
        for item in issues
        if "pull_request" not in item or item.get("pull_request") is None
    ]


def fetch_pull_requests(
    client: GiteaClient,
    owner: str,
    repo: str,
    state: str = "open",
) -> List[Dict]:
    path = "/repos/{0}/{1}/pulls".format(owner, repo)
    return client._paginate(path, {"state": state})


def fetch_branches(client: GiteaClient, owner: str, repo: str) -> List[Dict]:
    path = "/repos/{0}/{1}/branches".format(owner, repo)
    return client._paginate(path)


def fetch_commit_detail(
    client: GiteaClient,
    owner: str,
    repo: str,
    sha: str,
    include_code: bool = True,
) -> Dict:
    path = "/repos/{0}/{1}/git/commits/{2}".format(owner, repo, sha)
    params = {}
    if include_code:
        params["stat"] = True
        params["files"] = True
    detail = client._request("GET", path, params)
    if isinstance(detail, dict):
        return detail
    return {}


def fetch_file_content(
    client: GiteaClient,
    owner: str,
    repo: str,
    filepath: str,
    ref: Optional[str] = None,
) -> Dict:
    quoted_path = quote(filepath.replace("\\", "/"), safe="/")
    path = "/repos/{0}/{1}/contents/{2}".format(owner, repo, quoted_path)
    params = {"ref": ref} if ref else None
    content = client._request("GET", path, params)
    if not isinstance(content, dict):
        return {}
    decoded = decode_content_payload(content)
    if decoded is not None:
        content["decoded_content"] = decoded
    return content


def decode_content_payload(payload: Dict) -> Optional[str]:
    raw = payload.get("content")
    if not raw or payload.get("type") not in (None, "file"):
        return None
    if str(payload.get("encoding", "base64")).lower() != "base64":
        return str(raw)
    try:
        data = base64.b64decode(str(raw).encode("utf-8"), validate=False)
    except (ValueError, TypeError):
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def list_repositories(
    client: GiteaClient,
    query: str = "",
    limit: Optional[int] = None,
) -> List[RepoRef]:
    repos: List[RepoRef] = []
    page = 1
    per_page = 50
    while True:
        params = {"page": page, "limit": per_page}
        if query:
            params["q"] = query
        response = client._request("GET", "/repos/search", params)
        if isinstance(response, dict):
            items = response.get("data") or []
            total_count = response.get("total_count")
        elif isinstance(response, list):
            items = response
            total_count = None
        else:
            items = []
            total_count = None

        for item in items:
            repos.append(repo_ref_from_api(client.base_url, item))
            if limit is not None and len(repos) >= limit:
                return repos

        if len(items) < per_page:
            break
        if total_count is not None and len(repos) >= int(total_count):
            break
        page += 1
    return repos
