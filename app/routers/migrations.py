from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.migration_worker import run_migration
from app.models import MigrationJob, Repository
from app.schemas import MigrationCreate, MigrationOut

router = APIRouter(prefix="/migrations", tags=["Migrations"])


def find_active_job(repository_id: int, db: Session) -> MigrationJob | None:
    return (
        db.query(MigrationJob)
        .filter(MigrationJob.repository_id == repository_id, MigrationJob.status.in_(["pending", "in_progress"]))
        .first()
    )


@router.post("", response_model=MigrationOut, status_code=202)
def start_migration(data: MigrationCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    # 1. repo must exist
    repo = db.get(Repository, data.repository_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    # 2. this POC implements one full flow: GitHub -> GitLab
    if repo.provider != "github" or data.target_provider != "gitlab":
        raise HTTPException(status_code=400, detail="Only GitHub -> GitLab migration is supported in this POC")
    if not settings.gitlab_token:
        raise HTTPException(status_code=400, detail="GITLAB_TOKEN is not set")

    # 3. duplicate check: if a job is already running for this repo, return that job
    running_job = find_active_job(repo.id, db)
    if running_job:
        return running_job

    # 4. create new job as "pending"
    job = MigrationJob(repository_id=repo.id, target_provider=data.target_provider)
    db.add(job)
    try:
        db.commit()
    except IntegrityError:  # two requests at the same moment -> DB unique index lets only one in
        db.rollback()
        return find_active_job(repo.id, db)
    db.refresh(job)

    # 5. start the work in background, reply immediately
    background_tasks.add_task(run_migration, job.id)
    return job


@router.get("/{job_id}", response_model=MigrationOut)
def get_migration(job_id: int, db: Session = Depends(get_db)):
    job = db.get(MigrationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Migration job not found")
    return job
