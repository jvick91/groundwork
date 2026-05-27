"""
Health check endpoints (SPEC-007 §9).

GET /health        — liveness probe (process is running)
GET /health/ready  — readiness probe (DB is reachable)

Neither endpoint requires authentication or X-Organization-Id.
The `_check_database` dependency is injectable so tests can override it
without mocking internals.

TASK-014 adds `auth0_jwks` to the readiness checks dict when auth
middleware is wired up.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.database import Database
from app.core.security import fetch_jwks, jwks_cache_healthy

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


async def _check_jwks() -> str:
    """Ensure the JWKS cache is populated.  Returns 'ok' or 'error'.

    In stub mode the JWKS is never fetched; the check always returns 'ok'
    so the readiness probe does not block local development.
    """
    if settings.auth_stub_enabled:
        return "ok"
    if jwks_cache_healthy():
        return "ok"
    try:
        await fetch_jwks()
        return "ok"
    except Exception:
        return "error"


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

    Returns 503 if any check fails.
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
