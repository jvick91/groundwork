"""
Re-exports of commonly used FastAPI dependencies.

Import from here in routers to keep imports clean.
"""

from app.core.database import get_db
from app.core.security import get_auth_context, require_permission

__all__ = ["get_db", "get_auth_context", "require_permission"]
