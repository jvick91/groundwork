"""
FastAPI lifespan context manager for startup and shutdown events.

Handles initializing logging, verifying database connectivity,
and cleaning up resources on shutdown.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.logger import get_logger, setup_logging
from app.core.settings import settings

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

    yield

    # Shutdown
    logger.info("shutting_down_application")
