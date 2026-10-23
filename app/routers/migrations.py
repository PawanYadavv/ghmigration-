from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.migration_worker import run_migration
from app.models import MigrationJob, Repository
from app.schemas import MigrationCreate, MigrationOut

router = APIRouter(prefix="/migrations", tags=["Migrations"])


@router.post("", response_model=MigrationOut, status_code=202)
def start_migration(data: MigrationCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    # 1. repo must exist
    if not db.get(Repository, data.repository_id):
        raise HTTPException(status_code=404, detail="Repository not found")

    # 2. duplicate check: if a job is already running for this repo, return that job
    running_job = (
        db.query(MigrationJob)
        .filter(MigrationJob.repository_id == data.repository_id, MigrationJob.status.in_(["pending", "in_progress"]))
        .first()
    )
    if running_job:
        return running_job

    # 3. create new job as "pending"
    job = MigrationJob(repository_id=data.repository_id, target_provider=data.target_provider)
    db.add(job)
    db.commit()
    db.refresh(job)

    # 4. start the work in background, reply immediately
    background_tasks.add_task(run_migration, job.id)
    return job


@router.get("/{job_id}", response_model=MigrationOut)
def get_migration(job_id: int, db: Session = Depends(get_db)):
    job = db.get(MigrationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Migration job not found")
    return job
