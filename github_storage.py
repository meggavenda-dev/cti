import base64
import json
from typing import Any, Dict

import requests

GITHUB_API = "https://api.github.com"


def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def github_get_file(repo: str, path: str, token: str, branch: str = "main") -> Dict[str, Any]:
    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"
    r = requests.get(url, headers=_headers(token), params={"ref": branch}, timeout=30)

    if r.status_code == 404:
        return {"exists": False}

    r.raise_for_status()
    data = r.json()

    return {
        "exists": True,
        "sha": data.get("sha"),
        "content": data.get("content"),
        "encoding": data.get("encoding"),
    }


def github_put_file(repo: str, path: str, token: str, branch: str, content_bytes: bytes, commit_message: str) -> None:
    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"
    existing = github_get_file(repo=repo, path=path, token=token, branch=branch)

    payload = {
        "message": commit_message,
        "content": base64.b64encode(content_bytes).decode("utf-8"),
        "branch": branch,
    }

    if existing.get("exists") and existing.get("sha"):
        payload["sha"] = existing["sha"]

    r = requests.put(url, headers=_headers(token), data=json.dumps(payload), timeout=30)
    r.raise_for_status()


def github_get_json(repo: str, path: str, token: str, branch: str = "main", default=None):
    file_info = github_get_file(repo=repo, path=path, token=token, branch=branch)
    if not file_info.get("exists"):
        return default

    if file_info.get("encoding") != "base64" or not file_info.get("content"):
        return default

    raw = base64.b64decode(file_info["content"])
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return default


def github_put_json(repo: str, path: str, token: str, branch: str, data, commit_message: str):
    content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    github_put_file(
        repo=repo,
        path=path,
        token=token,
        branch=branch,
        content_bytes=content,
        commit_message=commit_message,
    )
