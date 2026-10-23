from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Repository
from app.providers import create_github_repo, fetch_repo
from app.schemas import ProviderName, RepositoryCreate, RepositoryList, RepositoryOut, RepositoryUpdate

router = APIRouter(prefix="/repositories", tags=["Repositories"])


def get_repo_or_404(repo_id: int, db: Session) -> Repository:
    repo = db.get(Repository, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo


def ensure_not_in_catalog(provider: str, owner: str, name: str, db: Session):
    exists = db.query(Repository).filter_by(provider=provider, owner=owner, name=name).first()
    if exists:
        raise HTTPException(status_code=409, detail="Repository already exists")


def save_repository(data: dict, db: Session) -> Repository:
    repo = Repository(**data)
    db.add(repo)
    try:
        db.commit()
    except IntegrityError:  # unique constraint (provider, owner, name) violated
        db.rollback()
        raise HTTPException(status_code=409, detail="Repository already exists")
    db.refresh(repo)
    return repo


@router.post("", response_model=RepositoryOut, status_code=201)
def create_repository(data: RepositoryCreate, db: Session = Depends(get_db)):
    # check our catalog first, so we don't create a repo on GitHub that we then can't save
    ensure_not_in_catalog(data.provider, data.owner, data.name, db)

    if data.provider == "github":
        repo_data = create_github_repo(data.owner, data.name, data.is_private)  # real repo on GitHub
    else:
        repo_data = data.model_dump()  # other providers are mocked -> only saved in our catalog
    return save_repository(repo_data, db)


@router.post("/import", response_model=RepositoryOut, status_code=201)
def import_repository(provider: ProviderName, owner: str, name: str, db: Session = Depends(get_db)):
    data = fetch_repo(provider, owner, name)
    return save_repository(data, db)



@router.get("", response_model=RepositoryList)
def list_repositories(
    provider: ProviderName | None = None,
    owner: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(Repository)
    if provider:
        query = query.filter(Repository.provider == provider)
    if owner:
        query = query.filter(Repository.owner == owner)

    total = query.count()
    items = query.order_by(Repository.id).offset((page - 1) * size).limit(size).all()
    return {"total": total, "page": page, "size": size, "items": items}


@router.get("/{repo_id}", response_model=RepositoryOut)
def get_repository(repo_id: int, db: Session = Depends(get_db)):
    
    return get_repo_or_404(repo_id, db)


@router.patch("/{repo_id}", response_model=RepositoryOut)
def update_repository(repo_id: int, data: RepositoryUpdate, db: Session = Depends(get_db)):
    repo = get_repo_or_404(repo_id, db)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(repo, field, value)
    db.commit()
    db.refresh(repo)
    return repo


@router.delete("/{repo_id}", status_code=204)
def delete_repository(repo_id: int, db: Session = Depends(get_db)):
    repo = get_repo_or_404(repo_id, db)
    db.delete(repo)
    db.commit()
