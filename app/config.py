from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5434/scm_catalog"
    github_token: str | None = None  # needs "repo" scope to create repos
    gitlab_token: str | None = None  # needs "api" scope to create projects and push code
    gitlab_url: str = "https://gitlab.com"
    http_timeout: float = 10.0  # seconds to wait for GitHub / GitLab API

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
