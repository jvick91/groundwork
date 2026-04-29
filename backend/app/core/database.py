"""
Async database engine and session management.

Provides a thread-safe Database singleton for deferred initialization,
the declarative Base with async support and naming conventions,
reusable model mixins, and the get_db dependency for FastAPI route injection.

Engine creation is deferred to application startup via Database.initialize(),
not at module import time. This ensures proper lifecycle management.
"""

import uuid
from datetime import datetime
from threading import Lock

from sqlalchemy import DateTime, MetaData, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.logger import get_logger

logger = get_logger(__name__)

# PostgreSQL naming convention for consistent constraint names in Alembic migrations
naming_convention = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase, AsyncAttrs):
    """Base class for all SQLAlchemy ORM models.

    Includes AsyncAttrs for safe lazy-load access in async context
    and a naming convention for predictable constraint names.
    """

    metadata = MetaData(naming_convention=naming_convention)


class IdMixin:
    """Provides a UUID primary key column."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )


class TimestampMixin:
    """Provides created_at and updated_at timestamp columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        server_default=None,
        onupdate=text("NOW()"),
    )


class SoftDeleteMixin:
    """Provides a deleted_at column for soft-delete support (HIPAA requirement)."""

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )


class Database:
    """Thread-safe singleton managing the async engine and session factory.

    Usage:
        # In lifespan startup:
        Database.initialize(settings.database_url, echo=settings.debug)

        # In dependencies:
        factory = Database.get_session_factory()

        # In lifespan shutdown:
        await Database.dispose()
    """

    _engine = None
    _session_factory = None
    _lock = Lock()

    @classmethod
    def initialize(cls, database_url: str, echo: bool = False, **engine_kwargs: object) -> None:
        """Initialize the async engine and session factory. Thread-safe.

        Extra keyword arguments are forwarded verbatim to
        ``create_async_engine``.  The primary use-case is passing
        ``poolclass=NullPool`` in the test suite to avoid event-loop
        mismatches caused by asyncpg connection pooling.
        """
        with cls._lock:
            if cls._engine is None:
                logger.info("initializing_database_engine", url=database_url.split("@")[-1])
                engine_config: dict = {"echo": echo, "pool_pre_ping": True, "future": True}
                engine_config.update(engine_kwargs)
                cls._engine = create_async_engine(database_url, **engine_config)
                cls._session_factory = async_sessionmaker(
                    bind=cls._engine,
                    class_=AsyncSession,
                    expire_on_commit=False,
                )

    @classmethod
    def get_session_factory(cls) -> async_sessionmaker[AsyncSession]:
        """Return the session factory, raising if not yet initialized."""
        with cls._lock:
            if cls._session_factory is None:
                raise RuntimeError("Database not initialized. Call Database.initialize() first.")
            return cls._session_factory

    @classmethod
    def get_engine(cls) -> AsyncEngine:
        """Return the async engine, raising if not yet initialized."""
        with cls._lock:
            if cls._engine is None:
                raise RuntimeError("Database not initialized. Call Database.initialize() first.")
            return cls._engine

    @classmethod
    async def dispose(cls) -> None:
        """Dispose of the engine and reset state. Call during shutdown."""
        with cls._lock:
            if cls._engine is not None:
                logger.info("disposing_database_engine")
                await cls._engine.dispose()
                cls._engine = None
                cls._session_factory = None
