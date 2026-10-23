# SCM Repository Catalog (POC)

FastAPI service to catalog repositories from GitHub, GitLab, Bitbucket and Azure DevOps,
and to migrate repositories from **GitHub to GitLab** as background jobs.

**One full end-to-end flow is real:**
1. `POST /repositories` with provider `github` → creates the repository **on GitHub** and saves it in the catalog.
2. `POST /migrations` → copies the repository (all branches + tags + history) **from GitHub to a new GitLab project**,
   tracked with status `pending → in_progress → completed / failed`.

Bitbucket and Azure DevOps (and GitLab as a *source*) are mocked.

## Setup

### 1. Tokens (`.env`)
Copy `.env.example` to `.env` and fill in:

| Variable | Where to create | Scope |
|---|---|---|
| `GITHUB_TOKEN` | GitHub → Settings → Developer settings → Personal access tokens → **Tokens (classic)** | `repo` |
| `GITLAB_TOKEN` | GitLab → Preferences → **Access tokens** | `api` |

### 2. Run with Docker
```
docker compose up --build
```
- Runs the database migrations (`alembic upgrade head`) and starts the API.
- Swagger UI: http://127.0.0.1:8001/docs

### Run locally (optional)
```
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
docker compose up -d db
alembic upgrade head
uvicorn app.main:app --reload --port 8001
```

### Run tests
```
python -m pytest -v
```
Tests use an in-memory SQLite DB and fake GitHub/GitLab/git calls, so no tokens or internet are needed.

## API

| Method | Endpoint | Description |
|---|---|---|
| POST | /repositories | Create repository (`github` → really created on GitHub; others → catalog only) |
| GET | /repositories?provider=&owner=&page=&size= | List with filters and pagination |
| GET | /repositories/{id} | Get repository |
| PATCH | /repositories/{id} | Update catalog fields |
| DELETE | /repositories/{id} | Remove from catalog (does **not** delete on GitHub) |
| POST | /repositories/import?provider=&owner=&name= | Fetch an existing repo from GitHub and save it |
| POST | /migrations | Start GitHub → GitLab migration (returns **202**, status `pending`) |
| GET | /migrations/{id} | Migration status, attempts, GitLab URL, error message |

### Demo
1. `POST /repositories` → `{"provider": "github", "owner": "<your-github-username>", "name": "test"}`
   → repo appears on your GitHub account.
2. `POST /migrations` → `{"repository_id": <id from step 1>, "target_provider": "gitlab"}` → `202 pending`
3. `GET /migrations/{id}` → `in_progress` → `completed`, with `target_url` pointing to the new GitLab project.

## Architecture

```
Client (Swagger) ──HTTP──► FastAPI
                            ├─ routers/       API layer: validation (Pydantic), status codes
                            ├─ providers.py   GitHub + GitLab API clients (timeout + retry), mocks
                            └─ migration_worker.py   background job: GitLab project → git clone --mirror → git push
                                  │
                PostgreSQL ◄──────┘ (SQLAlchemy, Alembic migrations)
```

## Design decisions
- **FastAPI + sync SQLAlchemy + PostgreSQL**, schema managed by **Alembic**.
- **Reliability**: every GitHub/GitLab API call has a 10s timeout and up to 3 retries with exponential backoff
  on network errors and 5xx. 4xx errors (not found, bad token) fail immediately with a clear message.
- **Migration job**: FastAPI BackgroundTasks. The worker retries the whole migration up to 3 times
  (`attempts` column) for temporary errors. Tokens are never stored in error messages.
- **Duplicates**:
  - Same repository can't be added twice → `409` (unique constraint on provider + owner + name).
  - Only one active migration per repository: the API returns the running job, and a **partial unique index**
    in the database guarantees it even when two requests arrive at the same moment.
- **Delete** only removes the repository from the catalog. Deleting real repositories is irreversible,
  so it is intentionally not exposed.
- Migration pushes `refs/heads/*` and `refs/tags/*` (all branches and tags). GitHub's internal pull request refs are skipped.

## Improvements (future)
- Celery/ARQ + Redis for durable background jobs (BackgroundTasks loses jobs if the server restarts)
- Real GitLab/Bitbucket/Azure DevOps clients as sources, and more migration directions
- Migrate issues, pull requests and wiki (today: code, branches, tags, history)
- Async httpx, caching, smarter rate-limit handling (`X-RateLimit-Reset`)
- Authentication, structured logging, monitoring, more tests
