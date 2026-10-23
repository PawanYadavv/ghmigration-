import time
from urllib.parse import quote

import httpx
from fastapi import HTTPException

from app.config import settings

GITHUB_API = "https://api.github.com"


def request_with_retry(method: str, url: str, **kwargs) -> httpx.Response:
    """Call an external API with a timeout, retrying up to 3 times on network errors / 5xx."""
    for attempt in range(3):  # retry up to 3 times
        try:
            response = httpx.request(method, url, timeout=settings.http_timeout, follow_redirects=True, **kwargs)
            if response.status_code < 500:
                return response  # got a proper answer -> stop retrying
        except httpx.RequestError:  # timeout or network problem -> try again
            pass
        if attempt < 2:
            time.sleep(2**attempt)  # wait 1s, then 2s (exponential backoff)

    host = url.split("/")[2]
    raise HTTPException(status_code=503, detail=f"{host} is not reachable, try again later")


# ---------------- GitHub (real API) ----------------

def github_headers() -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    return headers


def check_github_errors(response: httpx.Response, not_found_message: str):
    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="GitHub token is invalid")
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail=not_found_message)
    if response.status_code in (403, 429):
        raise HTTPException(status_code=403, detail="GitHub refused: rate limit exceeded or token lacks permission")


def github_repo_to_dict(data: dict) -> dict:
    return {
        "provider": "github",
        "owner": data["owner"]["login"],
        "name": data["name"],
        "url": data["html_url"],
        "default_branch": data["default_branch"],
        "is_private": data["private"],
        "stars": data["stargazers_count"],
    }


def fetch_github_repo(owner: str, name: str) -> dict:
    """Get details of an EXISTING GitHub repo."""
    response = request_with_retry("GET", f"{GITHUB_API}/repos/{owner}/{name}", headers=github_headers())
    check_github_errors(response, "Repository not found on GitHub")
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Unexpected response from GitHub: {response.status_code}")
    return github_repo_to_dict(response.json())


def create_github_repo(owner: str, name: str, is_private: bool) -> dict:
    """Create a NEW repo on GitHub (under your user, or under an organization)."""
    if not settings.github_token:
        raise HTTPException(status_code=400, detail="GITHUB_TOKEN is not set, cannot create repositories on GitHub")

    # who owns the token? -> decide between "my account" and "an organization"
    user = request_with_retry("GET", f"{GITHUB_API}/user", headers=github_headers())
    check_github_errors(user, "GitHub user not found")
    if owner.lower() == user.json()["login"].lower():
        url = f"{GITHUB_API}/user/repos"
    else:
        url = f"{GITHUB_API}/orgs/{owner}/repos"

    # auto_init=True -> GitHub adds a first commit (README), so the repo is not empty
    body = {"name": name, "private": is_private, "auto_init": True}
    response = request_with_retry("POST", url, headers=github_headers(), json=body)
    if response.status_code == 422:
        raise HTTPException(status_code=409, detail="Repository already exists on GitHub")
    check_github_errors(response, f"GitHub organization '{owner}' not found or you have no access")
    if response.status_code != 201:
        raise HTTPException(status_code=502, detail=f"Unexpected response from GitHub: {response.status_code}")
    return github_repo_to_dict(response.json())


# ---------------- GitLab (real API, used as migration target) ----------------

def create_gitlab_project(name: str, is_private: bool) -> dict:
    """Create an empty GitLab project (or reuse it if it already exists). Returns GitLab's project data."""
    if not settings.gitlab_token:
        raise HTTPException(status_code=400, detail="GITLAB_TOKEN is not set")

    api = f"{settings.gitlab_url}/api/v4"
    headers = {"PRIVATE-TOKEN": settings.gitlab_token}
    body = {"name": name, "path": name, "visibility": "private" if is_private else "public"}
    response = request_with_retry("POST", f"{api}/projects", headers=headers, json=body)

    if response.status_code == 400 and "has already been taken" in response.text:
        # project exists from an earlier migration -> reuse it
        username = request_with_retry("GET", f"{api}/user", headers=headers).json()["username"]
        response = request_with_retry("GET", f"{api}/projects/{quote(f'{username}/{name}', safe='')}", headers=headers)

    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="GitLab token is invalid")
    if response.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail=f"GitLab error {response.status_code}: {response.text[:200]}")
    return response.json()


# ---------------- Other providers (mocked) ----------------

def fake_repo(provider: str, owner: str, name: str) -> dict:
    # mock for gitlab / bitbucket / azure_devops (no real API call)
    return {
        "provider": provider,
        "owner": owner,
        "name": name,
        "url": f"https://{provider}.example.com/{owner}/{name}",
        "default_branch": "main",
        "is_private": False,
        "stars": 0,
    }


def fetch_repo(provider: str, owner: str, name: str) -> dict:
    if provider == "github":
        return fetch_github_repo(owner, name)
    return fake_repo(provider, owner, name)
