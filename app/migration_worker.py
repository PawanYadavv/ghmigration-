import random
import time

from app.database import SessionLocal
from app.models import MigrationJob

def run_migration(job_id: int):
    db = SessionLocal()  # own DB session, because the request is already finished
    job = db.get(MigrationJob, job_id)
    try:
        job.status = "in_progress"
        db.commit()

        time.sleep(5)  # POC: pretend we are copying the repo
        if random.random() < 0.2:  # POC: fail 20% of the time to show "failed" status
            raise Exception("Simulated failure: target provider not reachable")

        job.status = "completed"
        db.commit()
    except Exception as e:
        db.rollback()
        job.status = "failed"
        job.error_message = str(e)
        db.commit()
    finally:
        db.close()
