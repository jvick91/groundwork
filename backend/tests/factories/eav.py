"""
Test factories for EAV domain models.

Each factory inserts directly into the provided ``AsyncSession`` and flushes
so that the row's server-generated defaults are visible within the transaction.
No commit is issued — the caller (or the conftest rollback fixture) owns the
transaction boundary.
"""

import datetime as dt
from datetime import UTC

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Organization


async def create_organization(
    session: AsyncSession,
    *,
    name: str = "Test Organization",
    npi_number: str | None = None,
    tax_id: str | None = None,
    phone: str | None = None,
    address: str | None = None,
    tz: str = "UTC",
    is_active: bool = True,
) -> Organization:
    """Insert an Organization row and flush to populate server defaults.

    Parameters
    ----------
    tz:
        IANA timezone string (default ``"UTC"``). Named ``tz`` rather than
        ``timezone`` to avoid shadowing the stdlib ``datetime.timezone``.
    """
    org = Organization(
        name=name,
        npi_number=npi_number,
        tax_id=tax_id,
        phone=phone,
        address=address,
        timezone=tz,
        is_active=is_active,
        created_at=dt.datetime.now(tz=UTC),
    )
    session.add(org)
    await session.flush()
    return org
