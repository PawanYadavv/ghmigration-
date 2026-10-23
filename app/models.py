from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text

from app.database import Base


class Repository(Base):
    __tablename__ = "repositories" # table name

    id = Column(Integer, primary_key=True)
    provider = Column(String(50), nullable=False)  # github / gitlab / bitbucket / azure_devops
    owner = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    url = Column(String(500))
    default_branch = Column(String(100), default="main")
    is_private = Column(Boolean, default=False)
    stars = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())

    # same repo can't be added twice
    __table_args__ = (UniqueConstraint("provider", "owner", "name"),)

# unique constraint is used to ensure that the combination of provider, owner, and name is unique across the table. This prevents duplicate entries for the same repository.
class MigrationJob(Base):
    __tablename__ = "migration_jobs"

    id = Column(Integer, primary_key=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    target_provider = Column(String(50), nullable=False)
    status = Column(String(20), default="pending")  # pending / in_progress / completed / failed
    attempts = Column(Integer, default=0)  # how many times the worker tried
    target_url = Column(String(500))  # link to the migrated repo (e.g. on GitLab)
    error_message = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # only ONE pending/in_progress job per repo -> database itself blocks duplicate migrations
    __table_args__ = (
        Index(
            "uq_one_active_migration_per_repo",
            "repository_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'in_progress')"),
            sqlite_where=text("status IN ('pending', 'in_progress')"),
        ),
    )
