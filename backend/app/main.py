"""
FastAPI application factory.

Creates and configures the FastAPI app with middleware, exception handlers,
and the health check endpoint. Domain routers are added per phase.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import GroundworkError
from app.core.lifespan import lifespan
from app.core.logger import get_logger
from app.core.settings import settings
from app.routers import health as health_router

logger = get_logger(__name__)

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

    # Domain errors — GroundworkError subclasses (SPEC-007 §7.3)
    @app.exception_handler(GroundworkError)
    async def groundwork_error_handler(
        request: Request, exc: GroundworkError
    ) -> JSONResponse:
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
            details.append({
                "field": ".".join(field_parts) if field_parts else "body",
                "message": error.get("msg", "Invalid value."),
                "code": error.get("type", "value_error"),
            })
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
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
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
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
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

    # TODO: Phase 1 - Include EAV routers
    # TODO: Phase 2 - Include Identity/RBAC routers
    # TODO: Phase 3 - Include Scheduling routers
    # TODO: Phase 4 - Include Clinical, Billing, Compliance routers
    # TODO: Phase 5 - API hardening middleware

    return app


app = create_app()
