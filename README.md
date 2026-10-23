# SCM Repository Catalog (POC)

FastAPI service to catalog repositories from GitHub, GitLab, Bitbucket and Azure DevOps,
and run repository migration jobs in the background.

## Run with Docker
```
docker compose up --build
```
API docs (Swagger): http://127.0.0.1:8001/docs

## Run locally
```
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
docker compose up -d db
uvicorn app.main:app --reload --port 8001
```

## Run tests
```
python -m pytest -v
```

## API
| Method | Endpoint | Description |
|---|---|---|
| POST | /repositories | Create repository |
| GET | /repositories?provider=&owner=&page=&size= | List with filters and pagination |
| GET | /repositories/{id} | Get repository |
| PATCH | /repositories/{id} | Update repository |
| DELETE | /repositories/{id} | Delete repository |
| POST | /repositories/import?provider=&owner=&name= | Fetch repo from GitHub (others mocked) and save |
| POST | /migrations | Start migration job (returns 202, status pending) |
| GET | /migrations/{id} | Check migration status |

## Design decisions
- **FastAPI + sync SQLAlchemy + PostgreSQL** – simple and easy to read for a POC.
- **GitHub** – real API call with 10s timeout and 3 retries (exponential backoff) on network errors / 5xx.
  GitLab, Bitbucket and Azure DevOps are mocked.
- **Migrations** – run with FastAPI BackgroundTasks. Status: pending → in_progress → completed / failed.
  The copy step is simulated (5s wait, 20% random failure).
- **Duplicates** – same repo can't be added twice (DB unique constraint → 409).
  A second migration request for a repo with an active job returns the existing job.

## Improvements (future)
- Celery/ARQ + Redis for durable background jobs (BackgroundTasks loses jobs on restart)
- Partial unique index in DB to fully prevent duplicate migrations under concurrent requests
- Real migration with `git clone --mirror` / `git push --mirror`, plus automatic retry of failed jobs
- Alembic for database migrations instead of `create_all`
- Real GitLab/Bitbucket/Azure clients, async httpx, caching, rate-limit handling
- Authentication, logging, monitoring, more tests
