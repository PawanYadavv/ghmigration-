from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5434/scm_catalog"
    github_token: str | None = None
    github_timeout: float = 10.0

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
