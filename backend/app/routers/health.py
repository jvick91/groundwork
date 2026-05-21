"""
Health check endpoints (SPEC-007 §9).

GET /health        — liveness probe (process is running)
GET /health/ready  — readiness probe (DB and JWKS reachable)

Neither endpoint requires authentication or X-Organization-Id.
The ``_check_database`` and ``_check_jwks`` dependencies are injectable so
tests can override them without mocking internals.

# adr-bypass: adr-009-router-no-sqlalchemy-import - health probe SELECT 1; no aggregate service.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.database import Database
from app.core.dependencies import get_jwks_resolver
from app.core.security import JWKSResolver

router = APIRouter(prefix="/health", tags=["health"])


# ---------------------------------------------------------------------------
# Dependencies — overridable in tests
# ---------------------------------------------------------------------------


async def _check_database() -> str:
    """Probe the database with SELECT 1.  Returns 'ok' or 'error'."""
    try:
        engine = Database.get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "error"


async def _check_jwks(
    resolver: JWKSResolver = Depends(get_jwks_resolver),
) -> str:
    """Probe the JWKS resolver.  Returns 'ok' when at least one key is loadable.

    In stub mode (``auth_stub_enabled = True``) we report ``ok`` without
    touching the resolver — the readiness endpoint should not depend on
    Auth0 connectivity in local dev or in test environments that don't
    care about JWT validation.
    """
    if settings.auth_stub_enabled:
        return "ok"
    return await resolver.health()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def liveness() -> dict[str, str]:
    """Liveness probe — returns 200 if the process is running."""
    return {"status": "ok", "version": settings.app_version}


@router.get("/ready")
async def readiness(
    database: str = Depends(_check_database),
    auth0_jwks: str = Depends(_check_jwks),
) -> JSONResponse:
    """Readiness probe — returns 200 when all dependencies are healthy.

    Returns 503 if any check fails.  TASK-014 adds the ``auth0_jwks`` key
    alongside the existing ``database`` check; the response envelope is
    unchanged.
    """
    checks: dict[str, str] = {
        "database": database,
        "auth0_jwks": auth0_jwks,
    }

    all_ok = all(v == "ok" for v in checks.values())

    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={
            "status": "ready" if all_ok else "unhealthy",
            "checks": checks,
        },
    )
