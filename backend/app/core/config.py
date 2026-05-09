"""
Application settings using pydantic-settings.

Loads configuration from environment variables and .env.backend file.
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

    # Test database
    test_database_url: str = (
        "postgresql+asyncpg://groundwork:groundwork@db-test:5432/groundwork_test"
    )

    # Auth0
    auth0_domain: str = ""
    auth0_audience: str = ""
    auth0_issuer: str = ""

    # Stubs
    # Until TASK-014 (auth middleware) and TASK-015 (permission resolution) land,
    # auth-related dependencies short-circuit to a fixed test identity. This flag
    # is the single switch those tasks flip off.
    auth_stub_enabled: bool = True

    # Feature flags
    # Gated behind TASK-019 (auto-permission generation). When False, POST
    # /entity-types returns 501. GET/PATCH/DELETE on system/seed types always work.
    custom_entity_types_enabled: bool = False

    @property
    def auth0_issuer_url(self) -> str:
        if self.auth0_issuer:
            return self.auth0_issuer
        return f"https://{self.auth0_domain}/"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # Logging
    log_level: str = "INFO"
    log_json: bool = True


settings = Settings()
