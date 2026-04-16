"""
Application settings using pydantic-settings.

Loads configuration from environment variables and .env.backend file.
All services (FastAPI, Celery worker, Celery beat) import this module.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.backend",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "Groundwork"
    app_version: str = "0.1.0"
    debug: bool = False
    environment: str = "development"

    # Database (async - for FastAPI)
    database_url: str = "postgresql+asyncpg://groundwork:groundwork@db:5432/groundwork"

    # Database (sync - for Celery tasks)
    database_url_sync: str = "postgresql+psycopg2://groundwork:groundwork@db:5432/groundwork"

    # Test database
    test_database_url: str = "postgresql+asyncpg://groundwork:groundwork@db-test:5432/groundwork_test"

    # Auth0
    auth0_domain: str = ""
    auth0_audience: str = ""
    auth0_issuer: str = ""

    @property
    def auth0_issuer_url(self) -> str:
        if self.auth0_issuer:
            return self.auth0_issuer
        return f"https://{self.auth0_domain}/"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Celery
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # Logging
    log_level: str = "INFO"
    log_json: bool = True


settings = Settings()
