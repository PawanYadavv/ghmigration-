from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# only these values are allowed -> anything else returns 422 error automatically
ProviderName = Literal["github", "gitlab", "bitbucket", "azure_devops"]

#  schema.py - what api accept and returns
class RepositoryCreate(BaseModel):
    provider: ProviderName
    owner: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    url: str | None = None
    default_branch: str = "main"
    is_private: bool = False
    stars: int = Field(default=0, ge=0)


class RepositoryUpdate(BaseModel):
    # all optional -> user sends only the fields they want to change
    url: str | None = None
    default_branch: str | None = None
    is_private: bool | None = None
    stars: int | None = Field(default=None, ge=0)


class RepositoryOut(RepositoryCreate):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)  # allows returning SQLAlchemy objects


class RepositoryList(BaseModel):
    total: int
    page: int
    size: int
    items: list[RepositoryOut]


class MigrationCreate(BaseModel):
    repository_id: int
    target_provider: ProviderName

class MigrationOut(BaseModel):
    id: int
    repository_id: int
    target_provider: ProviderName
    status: str
    attempts: int | None
    target_url: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
    