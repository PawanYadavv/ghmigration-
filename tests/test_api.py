import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import providers
from app.database import Base, get_db
from app.main import app

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


# ---------- integration tests (call the API) ----------

def test_create_repository():
    response = client.post("/repositories", json={"provider": "github", "owner": "test", "name": "repo1"})
    assert response.status_code == 201
    assert response.json()["name"] == "repo1"


def test_duplicate_repository_returns_409():
    data = {"provider": "gitlab", "owner": "test", "name": "repo2"}
    client.post("/repositories", json=data)
    response = client.post("/repositories", json=data)
    assert response.status_code == 409


def test_invalid_provider_returns_422():
    response = client.post("/repositories", json={"provider": "facebook", "owner": "a", "name": "b"})
    assert response.status_code == 422


# ---------- unit tests (GitHub is faked, no real internet call) ----------

def test_github_repo_not_found(monkeypatch):
    monkeypatch.setattr(providers.httpx, "get", lambda *args, **kwargs: httpx.Response(404))
    with pytest.raises(HTTPException) as error:
        providers.fetch_github_repo("abc", "missing")
    assert error.value.status_code == 404


def test_github_retries_3_times_on_server_error(monkeypatch):
    calls = []

    def fake_get(*args, **kwargs):
        calls.append(1)
        return httpx.Response(500)

    monkeypatch.setattr(providers.httpx, "get", fake_get)
    monkeypatch.setattr(providers.time, "sleep", lambda seconds: None)  # don't actually wait
    with pytest.raises(HTTPException) as error:
        providers.fetch_github_repo("abc", "repo")
    assert len(calls) == 3  # retried 3 times
    assert error.value.status_code == 503
