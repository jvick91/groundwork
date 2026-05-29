"""
Invitation service (TASK-014F / ADR-011).

Orchestrates the send side of the invitation lifecycle:
  send()   — validate type-specific rules, call Auth0, create row, audit
  list()   — cursor-paginated list scoped to the requesting org
  get()    — single-row fetch visible to the requesting org
  resend() — rotate nonce, replace Auth0 invitation, refresh TTL, audit
  revoke() — set state=revoked, revoke Auth0 invitation, audit

PersonRole is NOT created here; that happens at accept (TASK-014G).

Auth0 integration is skipped gracefully when management=None (local dev /
stub mode), so the full happy-path test suite can run without live Auth0
credentials. auth0_invitation_id is left NULL in that case.

Cross-tenant enumeration prevention (ADR-011 §uniform-response):
  send() always returns the same {status, invitation_id} shape regardless
  of whether the email maps to an existing Person. The type 4 (cross_org)
  Person lookup is done internally and never reflected in the response.
"""

from __future__ import annotations

import secrets
import uuid as _uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    ConflictError,
    DomainValidationError,
    GoneError,
    NotFoundError,
    PermissionDeniedError,
    SlugNotFoundError,
)
from app.core.logger import get_logger
from app.core.pagination import paginate
from app.enums.identity import InvitationState, InvitationType
from app.models.eav import EntityInstance, Organization
from app.models.identity import Invitation, Person, PersonRole, Role
from app.schemas.identity import InvitationCreate
from app.schemas.pagination import PaginationMeta, PaginationParams
from app.services.audit_service import AuditWriter, _AuditScope
from app.services.auth0_management_service import Auth0ManagementService

logger = get_logger(__name__)

_NONCE_BYTES = 32


@dataclass
class InvitationAcceptResult:
    """Value object returned by ``InvitationService.accept_invitation``."""

    person: Person
    person_role: PersonRole


class InvitationService:
    """Use-case orchestrator for the Invitation aggregate."""

    def __init__(
        self,
        session: AsyncSession,
        audit: AuditWriter,
        tenant_id: UUID,
        actor_id: UUID,
        management: Auth0ManagementService | None = None,
    ) -> None:
        self._session = session
        self._audit = audit
        self._tenant_id = tenant_id
        self._actor_id = actor_id
        self._management = management

    # ------------------------------------------------------------------
    # Public use-case methods
    # ------------------------------------------------------------------

    async def send(self, data: InvitationCreate) -> Invitation:
        """Create and dispatch a new invitation.

        Validates type-specific rules, calls Auth0 (if configured), stores
        the Invitation row, and writes an audit entry.

        Raises:
            ConflictError (409): A pending invitation for this email already
                                 exists in the requesting org.
            PermissionDeniedError (403): Type 3 caller lacks system_admin role.
        """
        org = await self._get_org()
        actor = await self._get_actor()
        inviter_name = f"{actor.first_name} {actor.last_name}"

        # --- Type-specific validation ---
        if data.type == InvitationType.SYSTEM_ADMIN:
            await self._assert_actor_is_system_admin()

        # --- Type 4: add existing Person to Auth0 org first ---
        auth0_user_id_for_org: str | None = None
        if data.type == InvitationType.CROSS_ORG and org.auth_provider_org_id:
            person = await self._find_person_by_email(str(data.email))
            if person is not None and person.auth_subject is not None:
                auth0_user_id_for_org = person.auth_subject
                if self._management is not None:
                    await self._management.add_organization_member(
                        org.auth_provider_org_id, auth0_user_id_for_org
                    )
                    logger.info(
                        "invitation_cross_org_member_added",
                        auth0_org_id=org.auth_provider_org_id,
                        auth0_user_id=auth0_user_id_for_org,
                    )

        # --- Create Auth0 invitation ---
        auth0_invitation_id: str | None = None
        if self._management is not None and org.auth_provider_org_id:
            auth0_inv = await self._management.create_organization_invitation(
                org.auth_provider_org_id,
                inviter_name=inviter_name,
                invitee_email=str(data.email),
                client_id=settings.auth0_spa_client_id,
                ttl_seconds=settings.invitation_ttl_seconds,
            )
            auth0_invitation_id = auth0_inv.get("id")
            logger.info(
                "invitation_auth0_created",
                auth0_invitation_id=auth0_invitation_id,
            )

        # --- Store the Invitation row ---
        now = datetime.now(tz=UTC)
        expires_at = now + timedelta(seconds=settings.invitation_ttl_seconds)
        nonce = secrets.token_urlsafe(_NONCE_BYTES)

        first_name: str | None = getattr(data, "first_name", None)
        last_name: str | None = getattr(data, "last_name", None)
        planned_entity_instance_id: UUID | None = getattr(
            data, "planned_entity_instance_id", None
        )
        planned_entity_instance_payload: dict[str, Any] | None = getattr(
            data, "planned_entity_instance_payload", None
        )

        invitation = Invitation(
            organization_id=self._tenant_id,
            type=data.type,
            email=str(data.email),
            first_name=first_name,
            last_name=last_name,
            planned_role_slug=data.planned_role_slug,
            planned_entity_instance_id=planned_entity_instance_id,
            planned_entity_instance_payload=planned_entity_instance_payload,
            nonce=nonce,
            state=InvitationState.PENDING,
            auth0_invitation_id=auth0_invitation_id,
            created_by_person_id=self._actor_id,
            expires_at=expires_at,
            created_at=now,
        )
        self._session.add(invitation)
        try:
            await self._session.flush()
        except Exception:
            # Most likely the partial unique index fired (duplicate pending email).
            raise ConflictError(
                f"A pending invitation for '{data.email}' already exists in this organisation.",
                details=[{"field": "email"}],
            )

        await self._audit.write(
            action="invitation.sent",
            resource_type="Invitation",
            resource_id=invitation.id,
            next_state=_invitation_snapshot(invitation),
        )
        return invitation

    async def list(
        self,
        params: PaginationParams,
        *,
        state: InvitationState | None = None,
    ) -> tuple[Sequence[Invitation], PaginationMeta]:
        """Return cursor-paginated invitations scoped to the requesting org."""
        stmt = select(Invitation).where(Invitation.organization_id == self._tenant_id)
        if state is not None:
            stmt = stmt.where(Invitation.state == state)
        return await paginate(
            self._session,
            stmt,
            params=params,
            sort_fields={
                "created_at": Invitation.created_at,
                "expires_at": Invitation.expires_at,
                "email": Invitation.email,
            },
            id_col=Invitation.id,
        )

    async def get(self, invitation_id: UUID) -> Invitation:
        """Return a single Invitation visible to this org or raise 404."""
        inv = await self._get_visible(invitation_id)
        if inv is None:
            raise NotFoundError("Invitation", invitation_id, action="read", actor_id=self._actor_id)
        return inv

    async def resend(self, invitation_id: UUID) -> Invitation:
        """Rotate the nonce and replace the Auth0 invitation.

        Raises:
            NotFoundError (404): Invitation not found for this org.
            ConflictError (409): Invitation is not in pending state.
        """
        inv = await self.get(invitation_id)
        if inv.state != InvitationState.PENDING:
            raise ConflictError(
                f"Cannot resend an invitation in state '{inv.state}'.",
                details=[{"field": "state"}],
            )

        org = await self._get_org()
        actor = await self._get_actor()

        # Revoke old Auth0 invitation
        if (
            self._management is not None
            and inv.auth0_invitation_id is not None
            and org.auth_provider_org_id is not None
        ):
            try:
                await self._management.revoke_organization_invitation(
                    org.auth_provider_org_id, inv.auth0_invitation_id
                )
            except Exception:
                logger.warning(
                    "invitation_resend_old_revoke_failed",
                    invitation_id=str(invitation_id),
                    auth0_invitation_id=inv.auth0_invitation_id,
                )

        # Create new Auth0 invitation
        auth0_invitation_id: str | None = None
        if self._management is not None and org.auth_provider_org_id:
            inviter_name = f"{actor.first_name} {actor.last_name}"
            auth0_inv = await self._management.create_organization_invitation(
                org.auth_provider_org_id,
                inviter_name=inviter_name,
                invitee_email=inv.email,
                client_id=settings.auth0_spa_client_id,
                ttl_seconds=settings.invitation_ttl_seconds,
            )
            auth0_invitation_id = auth0_inv.get("id")

        # Rotate nonce + update TTL + record new Auth0 ID
        now = datetime.now(tz=UTC)
        inv.nonce = secrets.token_urlsafe(_NONCE_BYTES)
        inv.auth0_invitation_id = auth0_invitation_id
        inv.expires_at = now + timedelta(seconds=settings.invitation_ttl_seconds)
        inv.updated_at = now
        await self._session.flush()

        await self._audit.write(
            action="invitation.resent",
            resource_type="Invitation",
            resource_id=inv.id,
            next_state=_invitation_snapshot(inv),
        )
        return inv

    async def revoke(self, invitation_id: UUID) -> None:
        """Set state=revoked and revoke the Auth0 invitation.

        Raises:
            NotFoundError (404): Invitation not found for this org.
            ConflictError (409): Invitation is not in pending state.
        """
        inv = await self.get(invitation_id)
        if inv.state != InvitationState.PENDING:
            raise ConflictError(
                f"Cannot revoke an invitation in state '{inv.state}'.",
                details=[{"field": "state"}],
            )

        org = await self._get_org()
        previous = _invitation_snapshot(inv)

        # Revoke Auth0 invitation (best-effort: log warning but do not fail)
        if (
            self._management is not None
            and inv.auth0_invitation_id is not None
            and org.auth_provider_org_id is not None
        ):
            try:
                await self._management.revoke_organization_invitation(
                    org.auth_provider_org_id, inv.auth0_invitation_id
                )
            except Exception:
                logger.warning(
                    "invitation_revoke_auth0_failed",
                    invitation_id=str(invitation_id),
                    auth0_invitation_id=inv.auth0_invitation_id,
                )

        now = datetime.now(tz=UTC)
        inv.state = InvitationState.REVOKED
        inv.revoked_at = now
        inv.updated_at = now
        await self._session.flush()

        await self._audit.write(
            action="invitation.revoked",
            resource_type="Invitation",
            resource_id=inv.id,
            previous_state=previous,
            next_state=_invitation_snapshot(inv),
        )

    # ------------------------------------------------------------------
    # Accept transaction (TASK-014G)
    # ------------------------------------------------------------------

    @staticmethod
    async def accept_invitation(
        session: AsyncSession,
        nonce: str,
        auth_subject: str,
        jwt_org_id: str | None,
        request_ip: str | None = None,
        request_ua: str | None = None,
    ) -> InvitationAcceptResult:
        """Accept an invitation by nonce.

        The full transaction is:
          1. Resolve invitation by nonce — 410 if terminal or expired.
          2. Verify ``Organization.auth_provider_org_id == jwt_org_id`` — 422 on mismatch.
          3. For types 1-3: create Person with ``auth_subject``.
             For type 4: look up existing Person by ``auth_subject`` - 409 if absent.
          4. For type 1 (provider): create EntityInstance from
             ``planned_entity_instance_payload`` or validate existing
             ``planned_entity_instance_id`` belongs to the same org.
          5. Resolve Role by ``planned_role_slug`` (org-scoped or system).
          6. Create PersonRole.
          7. Increment ``Person.permissions_version`` (ADR-012).
          8. Transition invitation → ``accepted``.
          9. Write ``AuditLog`` row (actor = newly-bound Person).

        All steps share one SQLAlchemy session; the caller / router commits.
        Any failure rolls back — the invitation stays ``pending`` and the
        nonce remains valid (until TTL).

        Raises:
            GoneError (410): Invitation not found, expired, revoked, or already accepted.
            DomainValidationError (422): JWT org_id does not match invitation org.
            ConflictError (409): Type-4 invite but no Person with matching auth_subject.
            SlugNotFoundError (404): Planned role slug not found.
            UnauthorizedError (401): JWT is invalid (validated upstream by router).
        """
        now = datetime.now(tz=UTC)

        # 1. Resolve invitation by nonce — no email lookup, ever.
        inv_row = await session.execute(
            select(Invitation).where(Invitation.nonce == nonce)
        )
        inv = inv_row.scalar_one_or_none()

        if (
            inv is None
            or inv.state != InvitationState.PENDING
            or inv.expires_at <= now
        ):
            raise GoneError(
                "Invitation not found, has expired, was revoked, or was already accepted."
            )

        # 2. Resolve org + verify org_id claim.
        org_row = await session.execute(
            select(Organization).where(Organization.id == inv.organization_id)
        )
        org = org_row.scalar_one_or_none()
        if org is None:
            raise RuntimeError(f"Invitation references unknown organization {inv.organization_id}.")

        # Only enforce when Auth0 is wired up (auth_provider_org_id is set).
        if org.auth_provider_org_id is not None and jwt_org_id != org.auth_provider_org_id:
            raise DomainValidationError(
                "JWT org_id does not match the invitation's organisation.",
                details=[{"field": "org_id"}],
            )

        # 3. Resolve or create Person — no email lookup anywhere in this path.
        person: Person
        if inv.type == InvitationType.CROSS_ORG:
            person_row = await session.execute(
                select(Person).where(
                    Person.auth_subject == auth_subject,
                    Person.deleted_at.is_(None),
                )
            )
            person = person_row.scalar_one_or_none()
            if person is None:
                raise ConflictError(
                    "No Person exists with this auth_subject. "
                    "A cross-org invitation requires an already-registered Person.",
                )
        else:
            # Types 1-3: first-time sign-in — create the Person row.
            person = Person(
                first_name=inv.first_name or "",
                last_name=inv.last_name or "",
                email=inv.email,
                auth_subject=auth_subject,
            )
            session.add(person)
            await session.flush()  # materialise person.id

        # 4. For type 1 (provider): resolve entity_instance_id.
        entity_instance_id: _uuid.UUID | None = inv.planned_entity_instance_id

        if inv.type == InvitationType.PROVIDER:
            if inv.planned_entity_instance_payload is not None:
                payload = inv.planned_entity_instance_payload
                raw_type_id = payload.get("entity_type_id")
                if raw_type_id is None:
                    raise DomainValidationError(
                        "planned_entity_instance_payload must include 'entity_type_id'.",
                        details=[{"field": "planned_entity_instance_payload.entity_type_id"}],
                    )
                entity_instance = EntityInstance(
                    entity_type_id=_uuid.UUID(str(raw_type_id)),
                    organization_id=inv.organization_id,
                    person_id=person.id,
                    is_active=True,
                )
                session.add(entity_instance)
                await session.flush()
                entity_instance_id = entity_instance.id
            elif inv.planned_entity_instance_id is not None:
                # Validate the referenced EntityInstance belongs to this org.
                ei_row = await session.execute(
                    select(EntityInstance).where(
                        EntityInstance.id == inv.planned_entity_instance_id,
                        EntityInstance.organization_id == inv.organization_id,
                        EntityInstance.deleted_at.is_(None),
                    )
                )
                if ei_row.scalar_one_or_none() is None:
                    raise DomainValidationError(
                        "planned_entity_instance_id does not belong to this organisation.",
                        details=[{"field": "planned_entity_instance_id"}],
                    )

        # 5. Resolve Role by planned_role_slug (org-scoped takes precedence over system).
        role_row = await session.execute(
            select(Role)
            .where(
                Role.slug == inv.planned_role_slug,
                or_(
                    Role.organization_id == inv.organization_id,
                    Role.organization_id.is_(None),
                ),
            )
            .order_by(Role.organization_id.nulls_last())
            .limit(1)
        )
        role = role_row.scalar_one_or_none()
        if role is None:
            raise SlugNotFoundError("Role", inv.planned_role_slug)

        # 6. Create PersonRole.
        person_role = PersonRole(
            organization_id=inv.organization_id,
            person_id=person.id,
            role_id=role.id,
            entity_instance_id=entity_instance_id,
            assigned_by_person_id=inv.created_by_person_id,
        )
        session.add(person_role)

        # 7. Increment permissions_version (ADR-012) — zero-staleness invalidation.
        person.permissions_version = (person.permissions_version or 0) + 1

        # 8. Transition invitation.
        previous_state = _invitation_snapshot(inv)
        inv.state = InvitationState.ACCEPTED
        inv.accepted_at = now
        inv.updated_at = now

        await session.flush()

        # 9. Audit — actor is the newly-bound Person.
        scope = _AuditScope(
            org_id=inv.organization_id,
            actor_id=person.id,
            ip_address=request_ip,
            user_agent=request_ua,
        )
        writer = AuditWriter(session=session, scope=scope)
        await writer.write(
            action="invitation.accepted",
            resource_type="Invitation",
            resource_id=inv.id,
            previous_state=previous_state,
            next_state=_invitation_snapshot(inv),
        )

        logger.info(
            "invitation_accepted",
            invitation_id=str(inv.id),
            person_id=str(person.id),
            invitation_type=inv.type,
        )

        return InvitationAcceptResult(person=person, person_role=person_role)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_org(self) -> Organization:
        result = await self._session.execute(
            select(Organization).where(Organization.id == self._tenant_id)
        )
        org = result.scalar_one_or_none()
        if org is None:
            raise RuntimeError(f"Organization {self._tenant_id} not found — data integrity error.")
        return org

    async def _get_actor(self) -> Person:
        result = await self._session.execute(
            select(Person).where(Person.id == self._actor_id, Person.deleted_at.is_(None))
        )
        actor = result.scalar_one_or_none()
        if actor is None:
            raise RuntimeError(f"Actor person {self._actor_id} not found — data integrity error.")
        return actor

    async def _assert_actor_is_system_admin(self) -> None:
        """Raise PermissionDeniedError if the actor does not hold system_admin."""
        result = await self._session.execute(
            select(PersonRole)
            .join(Role, Role.id == PersonRole.role_id)
            .where(
                PersonRole.person_id == self._actor_id,
                PersonRole.revoked_at.is_(None),
                Role.slug == "system_admin",
                Role.is_system_role.is_(True),
            )
            .limit(1)
        )
        if result.scalar_one_or_none() is None:
            raise PermissionDeniedError(
                "Only system_admins may send system_admin invitations.",
                actor_id=self._actor_id,
            )

    async def _find_person_by_email(self, email: str) -> Person | None:
        result = await self._session.execute(
            select(Person).where(
                Person.email == email,
                Person.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def _get_visible(self, invitation_id: UUID) -> Invitation | None:
        result = await self._session.execute(
            select(Invitation).where(
                Invitation.id == invitation_id,
                Invitation.organization_id == self._tenant_id,
            )
        )
        return result.scalar_one_or_none()


def _invitation_snapshot(inv: Invitation) -> dict[str, Any]:
    return {
        "id": str(inv.id),
        "organization_id": str(inv.organization_id),
        "type": inv.type,
        "email": inv.email,
        "planned_role_slug": inv.planned_role_slug,
        "state": inv.state,
        "auth0_invitation_id": inv.auth0_invitation_id,
        "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
    }
