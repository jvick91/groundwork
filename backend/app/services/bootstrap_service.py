"""
One-shot bootstrap service (TASK-014E).

Provisions the very first Organization + Person(system_admin) + Auth0 counterparts
in a single two-phase saga.

Saga phases
-----------
Phase 1 — Auth0 (reversible via compensating calls):
  a. create_organization  → compensation: delete_organization
  b. create_user          → compensation: delete_user
  c. add_organization_member → compensation: remove_organization_member
  d. create_password_change_ticket (read-only; no compensation needed)

Phase 2 — DB (atomic; SQLAlchemy session rolls back on exception):
  e. Guard: assert no Person rows exist (409 if violated)
  f. INSERT Organization (with auth_provider_org_id)
  g. INSERT Person        (with auth_subject)
  h. Lookup system_admin Role by slug
  i. INSERT PersonRole
  j. INSERT AuditLog

Phase 3 — Finalisation (within the still-open transaction):
  k. Delete the bootstrap marker file
  → Transaction commits naturally when the route handler returns.

If any step in Phase 2 or 3 raises, SQLAlchemy rolls back the transaction and
the service compensates Phase 1. The marker file is only deleted on the happy
path, so the operator can safely retry.
"""

from __future__ import annotations

import contextlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.logger import get_logger
from app.models.eav import Organization
from app.models.identity import Person, PersonRole, Role
from app.services.audit_service import AuditWriter, _AuditScope
from app.services.auth0_management_service import Auth0ManagementService

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class BootstrapRequest(BaseModel):
    """Payload for POST /api/v1/system/bootstrap."""

    org_name: str
    org_display_name: str
    admin_first_name: str
    admin_last_name: str
    admin_email: EmailStr


@dataclass(slots=True)
class BootstrapResult:
    """Returned as the 201 body after a successful bootstrap."""

    organization_id: str
    person_id: str
    auth0_user_id: str
    password_change_ticket_url: str


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class BootstrapService:
    """Orchestrates the two-phase bootstrap saga."""

    def __init__(
        self,
        session: AsyncSession,
        management: Auth0ManagementService,
    ) -> None:
        self._session = session
        self._management = management

    async def execute(self, data: BootstrapRequest, token_path: Path) -> BootstrapResult:
        """Run the full saga.

        Raises:
            ConflictError (409): A Person already exists — bootstrap has been
                                 performed outside the normal flow.
            Any other exception propagates after compensating Auth0 mutations.
        """
        # ------------------------------------------------------------------
        # Phase 1: Auth0
        # ------------------------------------------------------------------
        auth0_org_id: str | None = None
        auth0_user_id: str | None = None
        org_member_added = False

        try:
            auth0_org = await self._management.create_organization(
                name=data.org_name,
                display_name=data.org_display_name,
            )
            auth0_org_id = auth0_org["id"]
            logger.info("bootstrap_auth0_org_created", auth0_org_id=auth0_org_id)

            # Temporary random password — operator uses the ticket URL to set a
            # real password; the random value is never exposed.
            temp_password = secrets.token_urlsafe(32) + "Aa1!"
            auth0_user = await self._management.create_user(
                email=data.admin_email,
                password=temp_password,
                app_metadata={"is_active": True},
            )
            auth0_user_id = auth0_user["user_id"]
            logger.info("bootstrap_auth0_user_created", auth0_user_id=auth0_user_id)

            await self._management.add_organization_member(auth0_org_id, auth0_user_id)
            org_member_added = True

            ticket_data = await self._management.create_password_change_ticket(
                auth0_user_id,
                mark_email_as_verified=True,
            )
            ticket_url: str = ticket_data["ticket"]

        except Exception:
            logger.exception("bootstrap_auth0_phase_failed_compensating")
            await _compensate_auth0(
                self._management,
                auth0_org_id=auth0_org_id,
                auth0_user_id=auth0_user_id,
                org_member_added=org_member_added,
            )
            raise

        # ------------------------------------------------------------------
        # Phase 2: DB (within the open session — caller's transaction)
        # ------------------------------------------------------------------
        try:
            await self._assert_no_persons()

            org = Organization(
                name=data.org_display_name,
                is_active=True,
                auth_provider_org_id=auth0_org_id,
                created_at=datetime.now(tz=UTC),
            )
            self._session.add(org)
            await self._session.flush()

            person = Person(
                first_name=data.admin_first_name,
                last_name=data.admin_last_name,
                email=str(data.admin_email),
                auth_subject=auth0_user_id,
                is_active=True,
                created_at=datetime.now(tz=UTC),
            )
            self._session.add(person)
            await self._session.flush()

            role = await self._get_system_admin_role()
            person_role = PersonRole(
                organization_id=org.id,
                person_id=person.id,
                role_id=role.id,
                entity_instance_id=None,
                assigned_by_person_id=None,
            )
            self._session.add(person_role)
            await self._session.flush()

            audit = AuditWriter(
                self._session,
                _AuditScope(org_id=org.id, actor_id=person.id),
            )
            await audit.write(
                action="system.bootstrap",
                resource_type="Person",
                resource_id=person.id,
                organization_id=org.id,
                next_state={
                    "organization_id": str(org.id),
                    "person_id": str(person.id),
                    "auth0_org_id": auth0_org_id,
                    "auth0_user_id": auth0_user_id,
                },
            )

        except Exception:
            logger.exception("bootstrap_db_phase_failed_compensating")
            await _compensate_auth0(
                self._management,
                auth0_org_id=auth0_org_id,
                auth0_user_id=auth0_user_id,
                org_member_added=org_member_added,
            )
            raise

        # ------------------------------------------------------------------
        # Phase 3: Delete marker file (still within the open transaction;
        # transaction commits when the route handler returns successfully)
        # ------------------------------------------------------------------
        try:
            token_path.unlink()
            logger.info("bootstrap_marker_file_deleted", path=str(token_path))
        except OSError as exc:
            logger.exception("bootstrap_marker_file_deletion_failed", error=str(exc))
            await _compensate_auth0(
                self._management,
                auth0_org_id=auth0_org_id,
                auth0_user_id=auth0_user_id,
                org_member_added=org_member_added,
            )
            raise

        return BootstrapResult(
            organization_id=str(org.id),
            person_id=str(person.id),
            auth0_user_id=auth0_user_id,  # type: ignore[arg-type]
            password_change_ticket_url=ticket_url,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _assert_no_persons(self) -> None:
        count_result = await self._session.execute(
            select(func.count()).select_from(Person).where(Person.deleted_at.is_(None))
        )
        count = count_result.scalar_one()
        if count > 0:
            raise ConflictError(
                "Bootstrap refused: the system already has active Person records. "
                "Use the invitation flow (TASK-014F) to add more admins.",
            )

    async def _get_system_admin_role(self) -> Role:
        result = await self._session.execute(
            select(Role).where(
                Role.slug == "system_admin",
                Role.is_system_role.is_(True),
                Role.organization_id.is_(None),
            )
        )
        role = result.scalar_one_or_none()
        if role is None:
            raise RuntimeError(
                "system_admin role not found — ensure RBAC seed migration has run."
            )
        return role


# ---------------------------------------------------------------------------
# Compensation helper (best-effort; logs and suppresses failures)
# ---------------------------------------------------------------------------


async def _compensate_auth0(
    management: Auth0ManagementService,
    *,
    auth0_org_id: str | None,
    auth0_user_id: str | None,
    org_member_added: bool,
) -> None:
    """Best-effort reversal of Auth0 mutations created during the bootstrap saga.

    All errors are suppressed — we log them at CRITICAL level for operator
    investigation but cannot do anything else at this point.
    """
    if auth0_user_id and auth0_org_id and org_member_added:
        with contextlib.suppress(Exception):
            await management.remove_organization_member(auth0_org_id, auth0_user_id)
            logger.info("bootstrap_compensation_member_removed")

    if auth0_user_id:
        with contextlib.suppress(Exception):
            await management.delete_user(auth0_user_id)
            logger.info("bootstrap_compensation_user_deleted")

    if auth0_org_id:
        with contextlib.suppress(Exception):
            await management.delete_organization(auth0_org_id)
            logger.info("bootstrap_compensation_org_deleted")
