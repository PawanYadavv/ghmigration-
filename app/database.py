# db connection
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url) # connection pool to postgres
SessionLocal = sessionmaker(bind=engine, autoflush=False) # creating the session to connect to the database


class Base(DeclarativeBase):  # parent class for all table
    pass


def get_db():  #open a session for each request and close it after the request is completed, a dependency injection
    
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
