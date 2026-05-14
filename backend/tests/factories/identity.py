"""
Test factories for the Identity domain models.

Each factory inserts a row into the provided ``AsyncSession`` and flushes
so server-generated defaults are visible inside the transaction. No commit
is issued — the caller (or the conftest rollback fixture) owns the boundary.

These helpers exist for TASK-012 (Person CRUD) and intentionally sit
ahead of TASK-013 (role/permission seeds): each factory accepts overrides
so callers can shape exactly the test row they need without depending on
seed data that isn't yet committed to ``main``.
"""

from __future__ import annotations

import datetime as dt
import uuid
from datetime import UTC, date

from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.identity import RoleDomain
from app.models.identity import Person, PersonRole, Role


async def create_person(
    session: AsyncSession,
    *,
    first_name: str = "Test",
    last_name: str = "Person",
    email: str | None = None,
    auth_subject: str | None = None,
    phone: str | None = None,
    date_of_birth: date | None = None,
    is_active: bool = True,
) -> Person:
    """Insert a Person row and flush so server defaults are visible.

    ``email`` defaults to a uuid-namespaced value so concurrent tests do not
    collide on the unique constraint.
    """
    person = Person(
        first_name=first_name,
        last_name=last_name,
        email=email if email is not None else f"person-{uuid.uuid4().hex[:12]}@example.test",
        auth_subject=auth_subject,
        phone=phone,
        date_of_birth=date_of_birth,
        is_active=is_active,
        created_at=dt.datetime.now(tz=UTC),
    )
    session.add(person)
    await session.flush()
    return person


async def create_role(
    session: AsyncSession,
    *,
    name: str | None = None,
    slug: str | None = None,
    organization_id: uuid.UUID | None = None,
    primary_domain: RoleDomain = RoleDomain.ADMIN,
    is_system_role: bool = False,
) -> Role:
    """Insert a Role row scoped to ``organization_id`` (None = system role).

    ``slug`` defaults to a uuid-namespaced value to satisfy the
    ``UNIQUE(organization_id, slug)`` constraint across tests.
    """
    suffix = uuid.uuid4().hex[:8]
    role = Role(
        organization_id=organization_id,
        name=name if name is not None else f"Test Role {suffix}",
        slug=slug if slug is not None else f"test-role-{suffix}",
        primary_domain=primary_domain,
        is_system_role=is_system_role,
        created_at=dt.datetime.now(tz=UTC),
    )
    session.add(role)
    await session.flush()
    return role


async def create_person_role(
    session: AsyncSession,
    *,
    person_id: uuid.UUID,
    organization_id: uuid.UUID,
    role_id: uuid.UUID,
    entity_instance_id: uuid.UUID | None = None,
    revoked_at: dt.datetime | None = None,
) -> PersonRole:
    """Insert a PersonRole binding.

    ``revoked_at`` defaults to ``None`` (active assignment). Pass an explicit
    timestamp to model a historical / revoked assignment in tests that
    exercise the SPEC-002 §4 revocation rule.
    """
    person_role = PersonRole(
        person_id=person_id,
        organization_id=organization_id,
        role_id=role_id,
        entity_instance_id=entity_instance_id,
        revoked_at=revoked_at,
    )
    session.add(person_role)
    await session.flush()
    return person_role
