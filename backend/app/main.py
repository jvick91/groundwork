"""
FastAPI application factory.

Creates and configures the FastAPI app with middleware, exception handlers,
and the health check endpoint. Domain routers are added per phase.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.exceptions import GroundworkError
from app.core.lifespan import lifespan
from app.core.settings import settings


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

    # Exception handler for domain errors
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
                "detail": exc.detail,
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
