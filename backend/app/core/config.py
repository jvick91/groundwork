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

    # OIDC provider settings (vendor-neutral: Auth0, Keycloak, Cognito, …).
    # ``oidc_domain`` exists for legacy Auth0 deployments that want a
    # short-form (host-only) config; ``oidc_issuer`` is the full issuer URL.
    # When both are unset, authentication is unconfigured and every
    # protected request returns 401.
    oidc_domain: str = ""
    oidc_audience: str = ""
    oidc_issuer: str = ""

    # Test / local-dev override: when non-empty, the JWKS resolver uses this
    # PEM-encoded public key for every kid instead of fetching from the IdP.
    # Production must leave this empty so JWKS rotation works.
    auth_jwt_static_public_key_pem: str = ""

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
    def oidc_issuer_url(self) -> str:
        """Return the configured OIDC issuer URL, or derive one from the domain."""
        if self.oidc_issuer:
            return self.oidc_issuer
        return f"https://{self.oidc_domain}/"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # Logging
    log_level: str = "INFO"
    log_json: bool = True


settings = Settings()
