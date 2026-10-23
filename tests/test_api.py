import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import migration_worker, providers
from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import MigrationJob
from app.routers import repositories

# tests use a temporary in-memory SQLite DB -> no Postgres needed, real data is not touched
engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db  # swap real DB with test DB
client = TestClient(app)


def fake_github_repo(owner, name, is_private=False):
    return {
        "provider": "github",
        "owner": owner,
        "name": name,
        "url": f"https://github.com/{owner}/{name}",
        "default_branch": "main",
        "is_private": is_private,
        "stars": 0,
    }


def create_github_repo_in_catalog(monkeypatch, name):
    monkeypatch.setattr(repositories, "create_github_repo", fake_github_repo)
    response = client.post("/repositories", json={"provider": "github", "owner": "me", "name": name})
    return response.json()["id"]


# ---------- repository API ----------

def test_create_github_repository_creates_it_on_github(monkeypatch):
    calls = []

    def fake_create(owner, name, is_private):
        calls.append(name)
        return fake_github_repo(owner, name, is_private)

    monkeypatch.setattr(repositories, "create_github_repo", fake_create)
    response = client.post("/repositories", json={"provider": "github", "owner": "me", "name": "repo1"})
    assert response.status_code == 201
    assert response.json()["url"] == "https://github.com/me/repo1"
    assert calls == ["repo1"]  # GitHub API was called


def test_create_mocked_provider_is_saved_in_catalog_only():
    response = client.post("/repositories", json={"provider": "bitbucket", "owner": "team", "name": "repo1"})
    assert response.status_code == 201


def test_duplicate_repository_returns_409():
    data = {"provider": "gitlab", "owner": "test", "name": "repo2"}
    client.post("/repositories", json=data)
    response = client.post("/repositories", json=data)
    assert response.status_code == 409


def test_invalid_provider_returns_422():
    response = client.post("/repositories", json={"provider": "facebook", "owner": "a", "name": "b"})
    assert response.status_code == 422


# ---------- GitHub client (GitHub is faked, no real internet call) ----------

def test_github_repo_not_found(monkeypatch):
    monkeypatch.setattr(providers.httpx, "request", lambda *args, **kwargs: httpx.Response(404))
    with pytest.raises(HTTPException) as error:
        providers.fetch_github_repo("abc", "missing")
    assert error.value.status_code == 404


def test_github_retries_3_times_on_server_error(monkeypatch):
    calls = []

    def fake_request(*args, **kwargs):
        calls.append(1)
        return httpx.Response(500)

    monkeypatch.setattr(providers.httpx, "request", fake_request)
    monkeypatch.setattr(providers.time, "sleep", lambda seconds: None)  # don't actually wait
    with pytest.raises(HTTPException) as error:
        providers.fetch_github_repo("abc", "repo")
    assert len(calls) == 3  # retried 3 times
    assert error.value.status_code == 503


def test_create_github_repo_calls_github_api(monkeypatch):
    def fake_request(method, url, **kwargs):
        if url.endswith("/user"):
            return httpx.Response(200, json={"login": "me"})
        assert method == "POST" and url.endswith("/user/repos")
        repo = {"owner": {"login": "me"}, "name": kwargs["json"]["name"], "html_url": "https://github.com/me/test",
                "default_branch": "main", "private": False, "stargazers_count": 0}
        return httpx.Response(201, json=repo)

    monkeypatch.setattr(settings, "github_token", "fake-token")
    monkeypatch.setattr(providers.httpx, "request", fake_request)
    result = providers.create_github_repo("me", "test", False)
    assert result["url"] == "https://github.com/me/test"


# ---------- migrations ----------

@pytest.fixture
def worker_uses_test_db(monkeypatch):
    monkeypatch.setattr(migration_worker, "SessionLocal", TestingSession)
    monkeypatch.setattr(migration_worker.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(settings, "gitlab_token", "fake-token")


def test_migration_github_to_gitlab_completes(monkeypatch, worker_uses_test_db):
    repo_id = create_github_repo_in_catalog(monkeypatch, "mig1")
    monkeypatch.setattr(migration_worker, "migrate_github_to_gitlab", lambda repo: "https://gitlab.com/me/mig1")

    response = client.post("/migrations", json={"repository_id": repo_id, "target_provider": "gitlab"})
    assert response.status_code == 202
    assert response.json()["status"] == "pending"

    # TestClient runs the background task right after the response
    job = client.get(f"/migrations/{response.json()['id']}").json()
    assert job["status"] == "completed"
    assert job["target_url"] == "https://gitlab.com/me/mig1"


def test_migration_retries_then_fails(monkeypatch, worker_uses_test_db):
    repo_id = create_github_repo_in_catalog(monkeypatch, "mig2")

    def always_fail(repo):
        raise RuntimeError("git push failed")

    monkeypatch.setattr(migration_worker, "migrate_github_to_gitlab", always_fail)
    response = client.post("/migrations", json={"repository_id": repo_id, "target_provider": "gitlab"})

    job = client.get(f"/migrations/{response.json()['id']}").json()
    assert job["status"] == "failed"
    assert job["attempts"] == 3
    assert "git push failed" in job["error_message"]


def test_duplicate_migration_returns_existing_job(monkeypatch, worker_uses_test_db):
    repo_id = create_github_repo_in_catalog(monkeypatch, "mig3")
    db = TestingSession()
    running = MigrationJob(repository_id=repo_id, target_provider="gitlab", status="in_progress")
    db.add(running)
    db.commit()

    response = client.post("/migrations", json={"repository_id": repo_id, "target_provider": "gitlab"})
    assert response.json()["id"] == running.id  # no new job created
    db.close()


def test_only_github_to_gitlab_is_supported(monkeypatch, worker_uses_test_db):
    repo_id = create_github_repo_in_catalog(monkeypatch, "mig4")
    response = client.post("/migrations", json={"repository_id": repo_id, "target_provider": "bitbucket"})
    assert response.status_code == 400
