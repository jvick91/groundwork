"""
Invitation send tests (TASK-014F).

Named acceptance-criteria tests:
  - test_create_provider_invite_succeeds
  - test_create_admin_invite_succeeds
  - test_create_system_admin_invite_requires_system_admin_permission
  - test_create_cross_org_invite_adds_auth0_org_membership
  - test_duplicate_pending_invite_same_email_returns_409
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions import ConflictError, PermissionDeniedError
from app.enums.identity import InvitationState, InvitationType
from app.models.eav import Organization
from app.models.identity import Invitation, Person, PersonRole, Role
from app.schemas.identity import (
    AdminInvitationCreate,
    CrossOrgInvitationCreate,
    ProviderInvitationCreate,
    SystemAdminInvitationCreate,
)
from app.services.invitation_service import InvitationService
from app.services.auth0_management_service import Auth0ManagementService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_org(auth_provider_org_id: str = "auth0org_test") -> Organization:
    org = MagicMock(spec=Organization)
    org.id = uuid4()
    org.auth_provider_org_id = auth_provider_org_id
    return org


def make_actor(first_name: str = "Alice", last_name: str = "Admin") -> Person:
    actor = MagicMock(spec=Person)
    actor.id = uuid4()
    actor.first_name = first_name
    actor.last_name = last_name
    actor.email = "alice@example.com"
    actor.deleted_at = None
    return actor


def make_service(
    *,
    org: Organization | None = None,
    actor: Person | None = None,
    management: MagicMock | None = None,
    session_execute_side_effects: list | None = None,
) -> InvitationService:
    """Build an InvitationService with a mock session and configurable execute results."""
    if org is None:
        org = make_org()
    if actor is None:
        actor = make_actor()

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    # Default execute queue: [org_result, actor_result]
    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org

    actor_result = MagicMock()
    actor_result.scalar_one_or_none.return_value = actor

    effects = session_execute_side_effects or [org_result, actor_result]
    session.execute = AsyncMock(side_effect=effects)

    audit = MagicMock()
    audit.write = AsyncMock()

    return InvitationService(
        session=session,
        audit=audit,
        tenant_id=org.id,
        actor_id=actor.id,
        management=management,
    )


# ---------------------------------------------------------------------------
# Provider invite (type 1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_provider_invite_succeeds(mock_management: MagicMock) -> None:
    org = make_org()
    actor = make_actor()
    svc = make_service(org=org, actor=actor, management=mock_management)

    data = ProviderInvitationCreate(
        type=InvitationType.PROVIDER,
        email="provider@example.com",
        planned_role_slug="provider",
        first_name="Bob",
        last_name="Provider",
        planned_entity_instance_payload={"name": "Bob Provider", "entity_type_slug": "provider"},
    )
    invitation = await svc.send(data)

    assert invitation.type == InvitationType.PROVIDER
    assert invitation.state == InvitationState.PENDING
    assert invitation.email == "provider@example.com"
    assert invitation.planned_role_slug == "provider"
    assert invitation.auth0_invitation_id == "auth0inv_abc"
    assert invitation.organization_id == org.id
    mock_management.create_organization_invitation.assert_awaited_once()
    # Provider invite must NOT call add_organization_member
    mock_management.add_organization_member.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_invite_requires_entity_instance() -> None:
    """ProviderInvitationCreate must reject missing entity instance info."""
    with pytest.raises(Exception):
        ProviderInvitationCreate(
            type=InvitationType.PROVIDER,
            email="provider@example.com",
            planned_role_slug="provider",
            first_name="Bob",
            last_name="Provider",
            # No planned_entity_instance_id or planned_entity_instance_payload
        )


# ---------------------------------------------------------------------------
# Admin invite (type 2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_admin_invite_succeeds(mock_management: MagicMock) -> None:
    org = make_org()
    actor = make_actor()
    svc = make_service(org=org, actor=actor, management=mock_management)

    data = AdminInvitationCreate(
        type=InvitationType.ADMIN,
        email="admin@example.com",
        planned_role_slug="admin",
        first_name="Carol",
        last_name="Admin",
    )
    invitation = await svc.send(data)

    assert invitation.type == InvitationType.ADMIN
    assert invitation.state == InvitationState.PENDING
    assert invitation.planned_entity_instance_id is None
    assert invitation.planned_entity_instance_payload is None


# ---------------------------------------------------------------------------
# System_admin invite (type 3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_system_admin_invite_requires_system_admin_permission(
    mock_management: MagicMock,
) -> None:
    """An actor without system_admin role must be denied."""
    org = make_org()
    actor = make_actor()

    # _assert_actor_is_system_admin returns no row → PermissionDeniedError
    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org
    actor_result = MagicMock()
    actor_result.scalar_one_or_none.return_value = actor
    role_check_result = MagicMock()
    role_check_result.scalar_one_or_none.return_value = None  # not a system_admin

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock(side_effect=[org_result, actor_result, role_check_result])
    audit = MagicMock()
    audit.write = AsyncMock()

    svc = InvitationService(
        session=session,
        audit=audit,
        tenant_id=org.id,
        actor_id=actor.id,
        management=mock_management,
    )

    data = SystemAdminInvitationCreate(
        type=InvitationType.SYSTEM_ADMIN,
        email="sysadmin@example.com",
        planned_role_slug="system_admin",
        first_name="Dave",
        last_name="SysAdmin",
    )
    with pytest.raises(PermissionDeniedError):
        await svc.send(data)

    mock_management.create_organization_invitation.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_system_admin_invite_succeeds_for_system_admin(
    mock_management: MagicMock,
) -> None:
    """An actor with system_admin role may send a system_admin invitation."""
    org = make_org()
    actor = make_actor()

    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org
    actor_result = MagicMock()
    actor_result.scalar_one_or_none.return_value = actor
    # Role check returns a PersonRole row → actor is a system_admin
    role_check_result = MagicMock()
    role_check_result.scalar_one_or_none.return_value = MagicMock(spec=PersonRole)

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock(side_effect=[org_result, actor_result, role_check_result])
    audit = MagicMock()
    audit.write = AsyncMock()

    svc = InvitationService(
        session=session,
        audit=audit,
        tenant_id=org.id,
        actor_id=actor.id,
        management=mock_management,
    )

    data = SystemAdminInvitationCreate(
        type=InvitationType.SYSTEM_ADMIN,
        email="sysadmin@example.com",
        planned_role_slug="system_admin",
        first_name="Dave",
        last_name="SysAdmin",
    )
    invitation = await svc.send(data)

    assert invitation.type == InvitationType.SYSTEM_ADMIN
    mock_management.create_organization_invitation.assert_awaited_once()


# ---------------------------------------------------------------------------
# Cross-org invite (type 4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_cross_org_invite_adds_auth0_org_membership(
    mock_management: MagicMock,
) -> None:
    """Type 4 invite: existing Person with auth_subject → add to Auth0 org."""
    org = make_org(auth_provider_org_id="auth0org_target")
    actor = make_actor()
    existing_person = MagicMock(spec=Person)
    existing_person.auth_subject = "auth0|existing_user"
    existing_person.deleted_at = None

    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org
    actor_result = MagicMock()
    actor_result.scalar_one_or_none.return_value = actor
    person_lookup_result = MagicMock()
    person_lookup_result.scalar_one_or_none.return_value = existing_person

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock(side_effect=[org_result, actor_result, person_lookup_result])
    audit = MagicMock()
    audit.write = AsyncMock()

    svc = InvitationService(
        session=session,
        audit=audit,
        tenant_id=org.id,
        actor_id=actor.id,
        management=mock_management,
    )

    data = CrossOrgInvitationCreate(
        type=InvitationType.CROSS_ORG,
        email="existing@example.com",
        planned_role_slug="admin",
    )
    invitation = await svc.send(data)

    mock_management.add_organization_member.assert_awaited_once_with(
        "auth0org_target", "auth0|existing_user"
    )
    mock_management.create_organization_invitation.assert_awaited_once()
    assert invitation.type == InvitationType.CROSS_ORG


@pytest.mark.asyncio
async def test_create_cross_org_invite_no_existing_person_skips_member_add(
    mock_management: MagicMock,
) -> None:
    """Type 4 with no matching Person: skip add_member, still create invitation."""
    org = make_org(auth_provider_org_id="auth0org_target")
    actor = make_actor()

    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org
    actor_result = MagicMock()
    actor_result.scalar_one_or_none.return_value = actor
    person_lookup_result = MagicMock()
    person_lookup_result.scalar_one_or_none.return_value = None  # no matching person

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock(side_effect=[org_result, actor_result, person_lookup_result])
    audit = MagicMock()
    audit.write = AsyncMock()

    svc = InvitationService(
        session=session,
        audit=audit,
        tenant_id=org.id,
        actor_id=actor.id,
        management=mock_management,
    )

    data = CrossOrgInvitationCreate(
        type=InvitationType.CROSS_ORG,
        email="unknown@example.com",
        planned_role_slug="admin",
    )
    invitation = await svc.send(data)

    mock_management.add_organization_member.assert_not_awaited()
    mock_management.create_organization_invitation.assert_awaited_once()
    assert invitation.type == InvitationType.CROSS_ORG


# ---------------------------------------------------------------------------
# Duplicate pending invite (409)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_pending_invite_same_email_returns_409(
    mock_management: MagicMock,
) -> None:
    """flush() raises due to partial unique index → ConflictError propagated."""
    org = make_org()
    actor = make_actor()

    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org
    actor_result = MagicMock()
    actor_result.scalar_one_or_none.return_value = actor

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock(side_effect=Exception("unique constraint violation"))
    session.execute = AsyncMock(side_effect=[org_result, actor_result])
    audit = MagicMock()
    audit.write = AsyncMock()

    svc = InvitationService(
        session=session,
        audit=audit,
        tenant_id=org.id,
        actor_id=actor.id,
        management=mock_management,
    )

    data = AdminInvitationCreate(
        type=InvitationType.ADMIN,
        email="dup@example.com",
        planned_role_slug="admin",
        first_name="Dup",
        last_name="User",
    )
    with pytest.raises(ConflictError):
        await svc.send(data)


# ---------------------------------------------------------------------------
# No management service (stub mode)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_works_without_management_service() -> None:
    """Invitation row is created even when management=None (stub/dev mode)."""
    org = make_org()
    actor = make_actor()
    svc = make_service(org=org, actor=actor, management=None)

    data = AdminInvitationCreate(
        type=InvitationType.ADMIN,
        email="noauth@example.com",
        planned_role_slug="admin",
        first_name="No",
        last_name="Auth",
    )
    invitation = await svc.send(data)

    assert invitation.auth0_invitation_id is None
    assert invitation.state == InvitationState.PENDING
