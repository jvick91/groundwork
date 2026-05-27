"""
FastAPI application factory.

Creates and configures the FastAPI app with middleware, exception handlers,
and the health check endpoint. Domain routers are added per phase.
"""

from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.database import Database
from app.core.exceptions import GroundworkError
from app.core.lifespan import lifespan
from app.core.logger import get_logger
from app.core.request_logger import RequestLoggerMiddleware
from app.middleware.auth import AuthMiddleware
from app.routers import compliance as compliance_router
from app.routers import eav as eav_router
from app.routers import entity_instances as entity_instances_router
from app.routers import entity_types as entity_types_router
from app.routers import health as health_router
from app.routers import identity as identity_router
from app.services.audit_service import AuditWriter, _AuditScope

logger = get_logger(__name__)


def _resolve_org_for_failure_audit(request: Request) -> UUID | None:
    """Best-effort tenant lookup for the failure-audit row.

    The auth context is normally produced by the ``get_auth_context``
    dependency during request handling; the exception handler runs after
    the request session has rolled back, so we read whatever the auth
    middleware (or the stub) left on ``request.state``. Until TASK-014
    wires the real middleware, we fall back to the stub org id so local
    dev still produces failure audits.
    """
    auth = getattr(request.state, "auth", None)
    if auth is not None:
        return getattr(auth, "organization_id", None)
    if settings.auth_stub_enabled:
        from app.core.security import _STUB_ORG_ID

        return _STUB_ORG_ID
    return None


# Map common HTTP status codes to stable error codes from SPEC-007 §7.3.
_HTTP_STATUS_TO_ERROR_CODE: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
}

# Loc prefixes FastAPI injects to mark the source of a validation error.
# Stripped so the returned `field` matches the caller-visible field name
# (SPEC-007 §7.2 / §7.4 use `content.subjective`, not `body.content.subjective`).
_VALIDATION_LOC_PREFIXES = {"body", "query", "path", "header", "cookie"}


def create_app() -> FastAPI:
    """Build and return the FastAPI application instance."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/api/v1/docs" if settings.debug else None,
        redoc_url="/api/v1/redoc" if settings.debug else None,
        openapi_url="/api/v1/openapi.json" if settings.debug else None,
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Auth middleware — validates JWTs and populates request.state.jwt_claims.
    # Starlette middleware is executed in reverse registration order (last added
    # = outermost). AuthMiddleware must run AFTER RequestLoggerMiddleware so the
    # request logger sees the full response code including 401s from auth.
    app.add_middleware(AuthMiddleware)

    # Request logger — wraps outermost and sees the client-visible status code.
    # SPEC-006 §4 BR-08: PHI is stripped by the structlog phi_filter processor.
    app.add_middleware(RequestLoggerMiddleware)

    # Domain errors — GroundworkError subclasses (SPEC-007 §7.3).
    # Per ADR-009, this handler is the single owner of failure-audit writes.
    # When the exception carries audit-context fields, we open a *fresh*
    # session (the request session is rolling back) and write a row with
    # outcome="failure" before translating to HTTP. Any failure of the audit
    # write itself is logged but never masks the original error.
    @app.exception_handler(GroundworkError)
    async def groundwork_error_handler(request: Request, exc: GroundworkError) -> JSONResponse:
        if (
            exc.audit_action is not None
            and exc.audit_entity_type is not None
            and exc.audit_entity_id is not None
        ):
            org_id = _resolve_org_for_failure_audit(request)
            if org_id is not None:
                try:
                    session_factory = Database.get_session_factory()
                    async with session_factory() as fresh_session:
                        writer = AuditWriter(
                            fresh_session,
                            _AuditScope(
                                org_id=org_id,
                                actor_id=exc.audit_actor_id,
                                ip_address=request.client.host if request.client else None,
                                user_agent=request.headers.get("user-agent"),
                            ),
                        )
                        await writer.write(
                            action=exc.audit_action,
                            resource_type=exc.audit_entity_type,
                            resource_id=exc.audit_entity_id,
                            outcome="failure",
                            next_state={"error": exc.error, "message": exc.message},
                        )
                        await fresh_session.commit()
                except Exception:
                    logger.exception(
                        "failure_audit_write_failed",
                        original_error=exc.error,
                    )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.error,
                "message": exc.message,
                "status": exc.status_code,
                "details": exc.details,
            },
        )

    # Pydantic / FastAPI request validation errors — 422 with field details (SPEC-007 §7.2)
    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = []
        for error in exc.errors():
            loc = error.get("loc", ())
            # Strip the leading source segment (body/query/path/header/cookie) so the
            # returned `field` matches the caller-visible path (SPEC-007 §7.2, §7.4).
            field_parts: list[str] = []
            for idx, part in enumerate(loc):
                if idx == 0 and part in _VALIDATION_LOC_PREFIXES:
                    continue
                field_parts.append(str(part))
            # Never echo the submitted value — `input` may contain PHI (SPEC-007 §7.4).
            details.append(
                {
                    "field": ".".join(field_parts) if field_parts else "body",
                    "message": error.get("msg", "Invalid value."),
                    "code": error.get("type", "value_error"),
                }
            )
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "message": "Request validation failed.",
                "status": 422,
                "details": details,
            },
        )

    # HTTPException (unknown route 404, 405, hand-raised HTTPException) must also
    # return the canonical envelope (SPEC-007 §7.1 / TASK-003 objective).
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        error_code = _HTTP_STATUS_TO_ERROR_CODE.get(exc.status_code, "http_error")
        message = exc.detail if isinstance(exc.detail, str) else "HTTP error."
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": error_code,
                "message": message,
                "status": exc.status_code,
                "details": [],
            },
            headers=getattr(exc, "headers", None),
        )

    # Catch-all — never leak internals (SPEC-007 §7.3 internal_error).
    # Uses structlog so the project's PHI filter runs before emission.
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled_exception",
            method=request.method,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": "An unexpected error occurred.",
                "status": 500,
                "details": [],
            },
        )

    # Health endpoints — public, no auth (SPEC-007 §9)
    app.include_router(health_router.router, prefix="/api/v1")

    # Compliance domain — audit log read endpoints (SPEC-006 §6)
    app.include_router(compliance_router.router, prefix="/api/v1")

    # EAV domain — Organization CRUD (SPEC-001 §2)
    app.include_router(eav_router.router, prefix="/api/v1")

    # EAV domain — EntityType CRUD (SPEC-001 §6, TASK-010 Phase 1)
    app.include_router(entity_types_router.router, prefix="/api/v1")

    # EAV domain — EntityInstance CRUD (SPEC-001 §6, TASK-011C)
    app.include_router(entity_instances_router.router, prefix="/api/v1")

    # Identity domain — Person CRUD (SPEC-002 §8, TASK-012)
    app.include_router(identity_router.router, prefix="/api/v1")

    # TODO: Phase 1 - Include EntityAttribute router (TASK-010 Phase 2)
    # TODO: Phase 2 - Include remaining Identity/RBAC routers (Roles, Permissions, PersonRoles)
    # TODO: Phase 3 - Include Scheduling routers
    # TODO: Phase 4 - Include Clinical, Billing, Compliance routers
    # TODO: Phase 5 - API hardening middleware

    return app


app = create_app()
