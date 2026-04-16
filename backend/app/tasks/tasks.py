"""
Celery task definitions.

Tasks run in the Celery worker process, NOT inside the FastAPI process.
They must create their own synchronous SQLAlchemy sessions when they need
database access, since they run in a separate process from the async FastAPI app.

Task arguments must be JSON-serializable (strings, ints, UUIDs as strings, dicts).
Do not pass Pydantic models or ORM objects directly.

Candidate task areas from specs:
- Audit log writes (SPEC-006)
- Document processing callbacks
- Consent expiry checks (SPEC-006)
- Scheduled report generation
- Invoice batch operations (SPEC-005)
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.celery_app import celery_app
from app.core.settings import settings

_sync_engine = create_engine(settings.database_url_sync, pool_pre_ping=True)
_SyncSessionFactory = sessionmaker(bind=_sync_engine)


def get_sync_session() -> Session:
    """Create a synchronous SQLAlchemy session for use within Celery tasks.

    Usage:
        with get_sync_session() as session:
            # do work
            session.commit()
    """
    return _SyncSessionFactory()


# TODO: Add task definitions per phase as domain requirements surface.
# Example:
#
# @celery_app.task
# def write_audit_log(event_type: str, entity_id: str, payload: dict) -> None:
#     with get_sync_session() as session:
#         ...
