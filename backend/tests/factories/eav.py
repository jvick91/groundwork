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

from app.models.eav import Organization


async def create_organization(
    session: AsyncSession,
    *,
    name: str = "Test Organization",
    npi_number: str | None = None,
    tax_id: str | None = None,
    phone: str | None = None,
    address_line1: str | None = None,
    address_line2: str | None = None,
    city: str | None = None,
    state: str | None = None,
    postal_code: str | None = None,
    country: str = "US",
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
        address_line1=address_line1,
        address_line2=address_line2,
        city=city,
        state=state,
        postal_code=postal_code,
        country=country,
        timezone=tz,
        is_active=is_active,
        created_at=dt.datetime.now(tz=UTC),
    )
    session.add(org)
    await session.flush()
    return org
