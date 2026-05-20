"""
FastAPI lifespan context manager for startup and shutdown events.

Handles initializing the database engine, verifying connectivity,
setting up logging, and cleaning up resources on shutdown.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.core.database import Database
from app.core.logger import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown logic."""
    # Startup
    setup_logging(log_level=settings.log_level, log_json=settings.log_json)
    logger.info(
        "starting_application",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )

    _warn_on_dangerous_auth_config()

    Database.initialize(settings.database_url, echo=settings.debug)

    yield

    # Shutdown
    await Database.dispose()
    logger.info("shutting_down_application")


def _warn_on_dangerous_auth_config() -> None:
    """Surface misconfigurations that would silently accept invalid auth.

    Per ADR-010, the production shape is ``auth_stub_enabled = False`` AND
    ``auth_jwt_static_public_key_pem`` empty AND a real OIDC issuer
    (``auth0_issuer`` or ``auth0_domain``) configured. Tests use a
    containerized Keycloak instance and never set the static-PEM field.
    """
    if settings.auth_stub_enabled:
        if settings.environment.lower() in ("production", "prod", "staging"):
            logger.warning(
                "auth_stub_enabled_in_non_dev_environment",
                environment=settings.environment,
                hint="Set AUTH_STUB_ENABLED=False outside local development.",
            )
        return

    if settings.auth_jwt_static_public_key_pem:
        logger.warning(
            "auth_jwt_static_public_key_pem_set_with_stub_disabled",
            environment=settings.environment,
            hint=(
                "AUTH_JWT_STATIC_PUBLIC_KEY_PEM is a dev/test-only fallback. "
                "Production must use a real OIDC issuer (OIDC_DOMAIN or "
                "OIDC_ISSUER) so JWKS rotation works. See ADR-010."
            ),
        )

    if (
        not settings.auth_jwt_static_public_key_pem
        and not settings.oidc_issuer
        and not settings.oidc_domain
    ):
        logger.warning(
            "no_oidc_issuer_configured",
            environment=settings.environment,
            hint=(
                "AUTH_STUB_ENABLED=False but no OIDC issuer set. All "
                "authenticated requests will return 401. Configure OIDC_DOMAIN "
                "or OIDC_ISSUER."
            ),
        )
