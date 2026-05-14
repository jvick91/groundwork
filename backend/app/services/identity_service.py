"""Service for the Person aggregate (SPEC-002 §2, §8, §9).

Person is tenant-independent. Tenant scoping for read paths is enforced by
joining through ``PersonRole`` filtered to the requesting org with
``revoked_at IS NULL`` (SPEC-002 §9). Create does NOT scope to a tenant —
a freshly created Person is only visible to a given org once it receives a
``PersonRole`` (TASK-017).

Architecture follows ADR-009 amendment: services hold ``AsyncSession``
directly; every SQL statement for the aggregate lives at the bottom of
this file under ``# Query helpers``. The router never imports SQLAlchemy.

Audit (BR-07):
- create / update / delete all write ``AuditLog`` rows.
- ``date_of_birth`` is stripped from snapshots by ``filter_phi`` because the
  field name is in ``PHI_EXCLUDED_FIELDS`` (BR-08).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.pagination import paginate
from app.models.identity import Person, PersonRole
from app.schemas.identity import PersonCreate, PersonUpdate
from app.schemas.pagination import PaginationMeta, PaginationParams
from app.services.audit_service import AuditWriter


class PersonService:
    """Use-case orchestrator for the Person aggregate."""

    def __init__(
        self,
        session: AsyncSession,
        audit: AuditWriter,
        tenant_id: UUID,
        actor_id: UUID | None,
    ) -> None:
        self._session = session
        self._audit = audit
        self._tenant_id = tenant_id
        self._actor_id = actor_id

    # ------------------------------------------------------------------
    # Public use-case methods
    # ------------------------------------------------------------------

    async def list(self, params: PaginationParams) -> tuple[Sequence[Person], PaginationMeta]:
        """Return people with active PersonRole in this org (SPEC-002 §9).

        Joins through ``PersonRole`` so cross-tenant Person rows are invisible.
        Soft-deleted Person rows are excluded (BR-05). ``DISTINCT`` because a
        person can hold multiple active roles in one org.
        """
        return await self._list_page(params)

    async def get(self, person_id: UUID) -> Person:
        """Return a single Person visible to this org or raise 404.

        Visibility follows the same PersonRole join as ``list``: a person
        without an active PersonRole in the requesting org returns 404 to
        avoid leaking cross-tenant existence (SPEC-002 §9).
        """
        person = await self._get_visible(person_id)
        if person is None:
            raise NotFoundError("Person", person_id, action="read", actor_id=self._actor_id)
        return person

    async def create(self, data: PersonCreate) -> Person:
        """Insert a Person row.

        Person has no ``organization_id``; tenant scoping enters via
        ``PersonRole`` (TASK-017). The created person is not visible to this
        org via ``list`` / ``get`` until a role is assigned — that is the
        documented design (SPEC-002 §2 design note).

        Duplicate ``email`` or ``auth_subject`` raises ``ConflictError`` (409)
        before the DB unique constraint fires.
        """
        await self._assert_email_available(data.email)
        if data.auth_subject is not None:
            await self._assert_auth_subject_available(data.auth_subject)

        now = datetime.now(tz=UTC)
        person = Person(
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email,
            phone=data.phone,
            date_of_birth=data.date_of_birth,
            auth_subject=data.auth_subject,
            is_active=True,
            created_at=now,
        )
        await self._save(person)

        await self._audit.write(
            action="create",
            resource_type="Person",
            resource_id=person.id,
            next_state=_person_snapshot(person),
        )
        return person

    async def update(self, person_id: UUID, data: PersonUpdate) -> Person:
        """Apply a partial update (PATCH semantics) and write an audit entry.

        Tenant visibility is enforced — a person without a PersonRole in this
        org returns 404. Email / auth_subject changes are uniqueness-checked.
        """
        person = await self.get(person_id)
        previous = _person_snapshot(person)
        updates = data.model_dump(exclude_unset=True)

        new_email = updates.get("email")
        if new_email is not None and new_email != person.email:
            await self._assert_email_available(new_email, exclude_id=person.id)

        new_auth_subject = updates.get("auth_subject")
        if new_auth_subject is not None and new_auth_subject != person.auth_subject:
            await self._assert_auth_subject_available(new_auth_subject, exclude_id=person.id)

        for field, value in updates.items():
            setattr(person, field, value)

        person.updated_at = datetime.now(tz=UTC)
        await self._save(person)

        await self._audit.write(
            action="update",
            resource_type="Person",
            resource_id=person.id,
            previous_state=previous,
            next_state=_person_snapshot(person),
        )
        return person

    async def delete(self, person_id: UUID) -> None:
        """Soft-delete a Person (sets ``deleted_at``, BR-05).

        Tenant visibility is enforced through ``get`` — a person without an
        active PersonRole in this org returns 404. Once soft-deleted, the
        person is excluded from ``list`` and ``get`` regardless of role state.
        """
        person = await self.get(person_id)
        previous = _person_snapshot(person)

        now = datetime.now(tz=UTC)
        person.deleted_at = now
        person.updated_at = now
        await self._save(person)

        await self._audit.write(
            action="delete",
            resource_type="Person",
            resource_id=person.id,
            previous_state=previous,
            next_state=_person_snapshot(person),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _assert_email_available(
        self,
        email: str,
        *,
        exclude_id: UUID | None = None,
    ) -> None:
        """Raise 409 if another non-deleted Person row already has this email."""
        existing = await self._find_by_email(email, exclude_id=exclude_id)
        if existing is not None:
            raise ConflictError(
                f"A Person with email '{email}' already exists.",
                details=[{"field": "email"}],
            )

    async def _assert_auth_subject_available(
        self,
        auth_subject: str,
        *,
        exclude_id: UUID | None = None,
    ) -> None:
        """Raise 409 if another non-deleted Person row already binds this Auth0 sub."""
        existing = await self._find_by_auth_subject(auth_subject, exclude_id=exclude_id)
        if existing is not None:
            raise ConflictError(
                f"A Person with auth_subject '{auth_subject}' already exists.",
                details=[{"field": "auth_subject"}],
            )

    # ------------------------------------------------------------------
    # Query helpers — every SQL statement for this aggregate lives here.
    # ------------------------------------------------------------------

    async def _get_visible(self, person_id: UUID) -> Person | None:
        """Fetch a non-deleted Person that has an active role in this org."""
        stmt = (
            select(Person)
            .join(PersonRole, PersonRole.person_id == Person.id)
            .where(
                Person.id == person_id,
                Person.deleted_at.is_(None),
                PersonRole.organization_id == self._tenant_id,
                PersonRole.revoked_at.is_(None),
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def _list_page(self, params: PaginationParams) -> tuple[Sequence[Person], PaginationMeta]:
        stmt = (
            select(Person)
            .join(PersonRole, PersonRole.person_id == Person.id)
            .where(
                Person.deleted_at.is_(None),
                PersonRole.organization_id == self._tenant_id,
                PersonRole.revoked_at.is_(None),
            )
            .distinct()
        )
        return await paginate(
            self._session,
            stmt,
            params=params,
            sort_fields={
                "created_at": Person.created_at,
                "updated_at": Person.updated_at,
                "last_name": Person.last_name,
                "email": Person.email,
            },
            id_col=Person.id,
        )

    async def _find_by_email(self, email: str, *, exclude_id: UUID | None = None) -> Person | None:
        stmt = select(Person).where(Person.email == email, Person.deleted_at.is_(None))
        if exclude_id is not None:
            stmt = stmt.where(Person.id != exclude_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _find_by_auth_subject(
        self, auth_subject: str, *, exclude_id: UUID | None = None
    ) -> Person | None:
        stmt = select(Person).where(
            Person.auth_subject == auth_subject, Person.deleted_at.is_(None)
        )
        if exclude_id is not None:
            stmt = stmt.where(Person.id != exclude_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _save(self, person: Person) -> None:
        self._session.add(person)
        await self._session.flush()


def _person_snapshot(person: Person) -> dict[str, Any]:
    """Audit-shape snapshot of a Person.

    ``date_of_birth`` is intentionally omitted here even though
    ``filter_phi`` would also strip it — defence in depth (SPEC-006 §7).
    """
    return {
        "id": str(person.id),
        "auth_subject": person.auth_subject,
        "first_name": person.first_name,
        "last_name": person.last_name,
        "email": person.email,
        "phone": person.phone,
        "is_active": person.is_active,
        "deleted_at": person.deleted_at.isoformat() if person.deleted_at else None,
    }
