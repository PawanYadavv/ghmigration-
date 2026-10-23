from fastapi import FastAPI

from app.routers import migrations, repositories

# creating fastapi application
# tables are created by Alembic migrations (alembic upgrade head), not here
app = FastAPI(title="SCM Repository Catalog")
app.include_router(repositories.router)
app.include_router(migrations.router)


@app.get("/health")
def health():
    return {"status": "ok"}
