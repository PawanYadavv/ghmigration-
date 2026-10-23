import shutil
import subprocess
import tempfile
import time

from fastapi import HTTPException

from app.config import settings
from app.database import SessionLocal
from app.models import MigrationJob, Repository
from app.providers import create_gitlab_project

MAX_ATTEMPTS = 3


def hide_tokens(message: str) -> str:
    # never store/show tokens in error messages
    for token in (settings.github_token, settings.gitlab_token):
        if token:
            message = message.replace(token, "***")
    return message


def run_git(*args: str):
    result = subprocess.run(["git", *args], capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(hide_tokens(f"git {args[0]} failed: {result.stderr.strip()}"))


def migrate_github_to_gitlab(repo: Repository) -> str:
    """Copy all branches and tags of a GitHub repo to GitLab. Returns the GitLab project URL."""
    # 1. create an empty project on GitLab
    project = create_gitlab_project(repo.name, repo.is_private)

    # 2. URLs with tokens inside, so git can log in without asking for a password
    if settings.github_token:
        source = f"https://x-access-token:{settings.github_token}@github.com/{repo.owner}/{repo.name}.git"
    else:
        source = f"https://github.com/{repo.owner}/{repo.name}.git"  # works for public repos only
    target = project["http_url_to_repo"].replace("https://", f"https://oauth2:{settings.gitlab_token}@")

    # 3. download everything from GitHub, upload all branches + tags to GitLab
    workdir = tempfile.mkdtemp()
    try:
        run_git("clone", "--mirror", source, workdir)
        run_git("-C", workdir, "push", target, "+refs/heads/*:refs/heads/*", "+refs/tags/*:refs/tags/*")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)  # delete the temporary copy

    return project["web_url"]


def run_migration(job_id: int):
    db = SessionLocal()  # own DB session, because the request is already finished
    try:
        job = db.get(MigrationJob, job_id)
        repo = db.get(Repository, job.repository_id)
        job.status = "in_progress"
        db.commit()

        for attempt in range(1, MAX_ATTEMPTS + 1):
            job.attempts = attempt
            db.commit()
            try:
                job.target_url = migrate_github_to_gitlab(repo)
                job.status = "completed"
                job.error_message = None
                break
            except Exception as e:
                job.error_message = str(e)
                # 4xx (bad token, no permission) won't fix itself -> stop; otherwise retry with backoff
                permanent_error = isinstance(e, HTTPException) and e.status_code < 500
                if permanent_error or attempt == MAX_ATTEMPTS:
                    job.status = "failed"
                    break
                time.sleep(2**attempt)  # wait 2s, then 4s
        db.commit()
    finally:
        db.close()
