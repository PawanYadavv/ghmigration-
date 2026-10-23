import time

import httpx
from fastapi import HTTPException

from app.config import settings


def fetch_github_repo(owner: str, name: str) -> dict:
    url = f"https://api.github.com/repos/{owner}/{name}"
    headers = {}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    response = None
    for attempt in range(3):  # retry up to 3 times
        try:
            response = httpx.get(url, headers=headers, timeout=settings.github_timeout, follow_redirects=True)
            if response.status_code < 500:
                break  # got a proper answer -> stop retrying
        except httpx.RequestError:  # timeout or network problem -> try again
            pass  # if timeout ignore and pass to retry
        if attempt < 2:
            time.sleep(2**attempt)  # wait 1s, then 2s (exponential backoff)

    if response is None or response.status_code >= 500:
        raise HTTPException(status_code=503, detail="GitHub is not reachable, try again later")
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Repository not found on GitHub")
    if response.status_code in (403, 429):
        raise HTTPException(status_code=429, detail="GitHub rate limit exceeded")

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Unexpected response from GitHub: {response.status_code}")
    data = response.json()
    return {
        "provider": "github",
        "owner": data["owner"]["login"],
        "name": data["name"],
        "url": data["html_url"],
        "default_branch": data["default_branch"],
        "is_private": data["private"],
        "stars": data["stargazers_count"],
    }


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
