"""
Re-exports of commonly used FastAPI dependencies.

Import from here in routers to keep imports clean.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Database
from app.core.security import get_auth_context, require_permission


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session.

    Commits on success, rolls back on exception, and always closes the session.
    """
    session_factory = Database.get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


__all__ = ["get_db", "get_auth_context", "require_permission"]
