"""
Development-only seed data for the auth stub.

This module is invoked by the Docker entrypoint after Alembic migrations. It
keeps local endpoint testing from failing on audit FK constraints while the real
auth/RBAC implementation is still pending.
"""

import asyncio
from datetime import UTC, datetime

from app.core.database import Database
from app.core.security import _STUB_AUTH_SUBJECT, _STUB_ORG_ID, _STUB_PERSON_ID
from app.core.settings import settings
from app.models.models import Organization, Person

_DEV_ENVIRONMENTS = {"development", "dev", "local"}


async def seed_auth_stub_identity() -> None:
    """Create fixed local-dev Organization and Person rows for the auth stub."""
    if not settings.auth_stub_enabled or settings.environment not in _DEV_ENVIRONMENTS:
        return

    Database.initialize(settings.database_url, echo=settings.debug)
    session_factory = Database.get_session_factory()

    async with session_factory() as session:
        now = datetime.now(tz=UTC)

        org = await session.get(Organization, _STUB_ORG_ID)
        if org is None:
            session.add(
                Organization(
                    id=_STUB_ORG_ID,
                    name="Development Stub Organization",
                    timezone="UTC",
                    is_active=True,
                    created_at=now,
                )
            )

        person = await session.get(Person, _STUB_PERSON_ID)
        if person is None:
            session.add(
                Person(
                    id=_STUB_PERSON_ID,
                    auth_subject=_STUB_AUTH_SUBJECT,
                    first_name="Development",
                    last_name="Stub",
                    email="stub@groundwork.test",
                    is_active=True,
                    created_at=now,
                )
            )

        await session.commit()

    await Database.dispose()


if __name__ == "__main__":
    asyncio.run(seed_auth_stub_identity())
