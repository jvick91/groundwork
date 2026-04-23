"""
FastAPI application factory.

Creates and configures the FastAPI app with middleware, exception handlers,
and the health check endpoint. Domain routers are added per phase.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.exceptions import GroundworkError
from app.core.lifespan import lifespan
from app.core.settings import settings

logger = logging.getLogger(__name__)


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
            # Strip the leading "body" segment if present
            field_parts = [str(part) for part in loc if part != "body"]
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

    # Catch-all — never leak internals (SPEC-007 §7.3 internal_error)
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": "An unexpected error occurred.",
                "status": 500,
                "details": [],
            },
        )

    # Health check (no auth required)
    @app.get("/api/v1/health", tags=["health"])
    async def health_check():
        return {"status": "healthy", "version": settings.app_version}

    # TODO: Phase 1 - Include EAV routers
    # TODO: Phase 2 - Include Identity/RBAC routers
    # TODO: Phase 3 - Include Scheduling routers
    # TODO: Phase 4 - Include Clinical, Billing, Compliance routers
    # TODO: Phase 5 - API hardening middleware

    return app


app = create_app()
