from contextlib import asynccontextmanager

from fastapi import FastAPI
from app.routers import migrations, repositories
from app import models  # noqa: F401  (import so SQLAlchemy knows our tables)
from app.database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # runs once when the app starts: create tables if they don't exist
    Base.metadata.create_all(bind=engine)
    yield


# creating fastapi application
app = FastAPI(title="SCM Repository Catalog", lifespan=lifespan)
app.include_router(repositories.router)
app.include_router(migrations.router)

@app.get("/health")
def health():
    return {"status": "ok"}
