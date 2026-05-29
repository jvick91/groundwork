"""
Invitation resend and revoke tests (TASK-014F).

Named acceptance-criteria tests:
  - test_resend_rotates_nonce
  - test_revoke_invite_sets_revoked_state
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import ConflictError, NotFoundError
from app.enums.identity import InvitationState, InvitationType
from app.models.eav import Organization
from app.models.identity import Invitation, Person
from app.services.invitation_service import InvitationService
from app.services.auth0_management_service import Auth0ManagementService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_pending_invitation(
    org_id: uuid4 = None,
    nonce: str = "old-nonce-value",
    auth0_invitation_id: str = "auth0inv_old",
) -> MagicMock:
    inv = MagicMock(spec=Invitation)
    inv.id = uuid4()
    inv.organization_id = org_id or uuid4()
    inv.state = InvitationState.PENDING
    inv.email = "test@example.com"
    inv.type = InvitationType.ADMIN
    inv.nonce = nonce
    inv.auth0_invitation_id = auth0_invitation_id
    inv.planned_role_slug = "admin"
    inv.expires_at = datetime.now(tz=UTC) + timedelta(days=7)
    return inv


def make_service_with_invitation(
    invitation: MagicMock,
    management: MagicMock | None,
    *,
    org_auth_provider_id: str = "auth0org_test",
    actor_first: str = "Alice",
    actor_last: str = "Admin",
) -> tuple[InvitationService, MagicMock]:
    org = MagicMock(spec=Organization)
    org.id = invitation.organization_id
    org.auth_provider_org_id = org_auth_provider_id

    actor = MagicMock(spec=Person)
    actor.id = uuid4()
    actor.first_name = actor_first
    actor.last_name = actor_last
    actor.deleted_at = None

    # execute queue: visible_inv → org → actor
    inv_result = MagicMock()
    inv_result.scalar_one_or_none.return_value = invitation
    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org
    actor_result = MagicMock()
    actor_result.scalar_one_or_none.return_value = actor

    session = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock(side_effect=[inv_result, org_result, actor_result])

    audit = MagicMock()
    audit.write = AsyncMock()

    svc = InvitationService(
        session=session,
        audit=audit,
        tenant_id=org.id,
        actor_id=actor.id,
        management=management,
    )
    return svc, session


# ---------------------------------------------------------------------------
# Resend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resend_rotates_nonce(mock_management: MagicMock) -> None:
    inv = make_pending_invitation(nonce="old-nonce-value", auth0_invitation_id="auth0inv_old")
    original_nonce = inv.nonce
    svc, _ = make_service_with_invitation(inv, mock_management)

    updated = await svc.resend(inv.id)

    assert updated.nonce != original_nonce
    assert updated.auth0_invitation_id == "auth0inv_abc"  # new one from mock
    mock_management.revoke_organization_invitation.assert_awaited_once_with(
        "auth0org_test", "auth0inv_old"
    )
    mock_management.create_organization_invitation.assert_awaited_once()


@pytest.mark.asyncio
async def test_resend_refreshes_expires_at(mock_management: MagicMock) -> None:
    original_expires = datetime.now(tz=UTC) + timedelta(hours=1)
    inv = make_pending_invitation()
    inv.expires_at = original_expires
    svc, _ = make_service_with_invitation(inv, mock_management)

    updated = await svc.resend(inv.id)

    # expires_at must be refreshed to at least 7 days from now
    assert updated.expires_at > original_expires


@pytest.mark.asyncio
async def test_resend_fails_on_non_pending_invitation(mock_management: MagicMock) -> None:
    inv = make_pending_invitation()
    inv.state = InvitationState.REVOKED

    # Only need one execute for the get() call
    inv_result = MagicMock()
    inv_result.scalar_one_or_none.return_value = inv
    session = MagicMock()
    session.execute = AsyncMock(return_value=inv_result)
    audit = MagicMock()

    svc = InvitationService(
        session=session,
        audit=audit,
        tenant_id=inv.organization_id,
        actor_id=uuid4(),
        management=mock_management,
    )

    with pytest.raises(ConflictError):
        await svc.resend(inv.id)


@pytest.mark.asyncio
async def test_resend_without_management_still_rotates_nonce() -> None:
    inv = make_pending_invitation(auth0_invitation_id=None)
    original_nonce = inv.nonce
    svc, _ = make_service_with_invitation(inv, management=None)

    updated = await svc.resend(inv.id)

    assert updated.nonce != original_nonce
    assert updated.auth0_invitation_id is None


# ---------------------------------------------------------------------------
# Revoke
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_invite_sets_revoked_state(mock_management: MagicMock) -> None:
    inv = make_pending_invitation()

    # execute queue for revoke: _get_visible → _get_org (no actor needed for revoke)
    inv_result = MagicMock()
    inv_result.scalar_one_or_none.return_value = inv
    org = MagicMock(spec=Organization)
    org.id = inv.organization_id
    org.auth_provider_org_id = "auth0org_test"
    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org

    session = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock(side_effect=[inv_result, org_result])
    audit = MagicMock()
    audit.write = AsyncMock()

    svc = InvitationService(
        session=session,
        audit=audit,
        tenant_id=inv.organization_id,
        actor_id=uuid4(),
        management=mock_management,
    )
    await svc.revoke(inv.id)

    assert inv.state == InvitationState.REVOKED
    assert inv.revoked_at is not None
    mock_management.revoke_organization_invitation.assert_awaited_once_with(
        "auth0org_test", "auth0inv_old"
    )
    audit.write.assert_awaited_once()


@pytest.mark.asyncio
async def test_revoke_fails_on_non_pending_invitation() -> None:
    inv = make_pending_invitation()
    inv.state = InvitationState.ACCEPTED

    inv_result = MagicMock()
    inv_result.scalar_one_or_none.return_value = inv
    session = MagicMock()
    session.execute = AsyncMock(return_value=inv_result)
    audit = MagicMock()

    svc = InvitationService(
        session=session,
        audit=audit,
        tenant_id=inv.organization_id,
        actor_id=uuid4(),
    )

    with pytest.raises(ConflictError):
        await svc.revoke(inv.id)


@pytest.mark.asyncio
async def test_revoke_continues_even_if_auth0_revoke_fails(
    mock_management: MagicMock,
) -> None:
    """Auth0 revoke failure is logged and ignored — DB state is still updated."""
    from app.core.exceptions import Auth0ManagementError

    mock_management.revoke_organization_invitation = AsyncMock(
        side_effect=Auth0ManagementError("already revoked")
    )

    inv = make_pending_invitation()
    inv_result = MagicMock()
    inv_result.scalar_one_or_none.return_value = inv
    org = MagicMock(spec=Organization)
    org.id = inv.organization_id
    org.auth_provider_org_id = "auth0org_test"
    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org

    session = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock(side_effect=[inv_result, org_result])
    audit = MagicMock()
    audit.write = AsyncMock()

    svc = InvitationService(
        session=session,
        audit=audit,
        tenant_id=inv.organization_id,
        actor_id=uuid4(),
        management=mock_management,
    )
    await svc.revoke(inv.id)

    assert inv.state == InvitationState.REVOKED


# ---------------------------------------------------------------------------
# Not-found cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_404_for_unknown_invitation() -> None:
    inv_result = MagicMock()
    inv_result.scalar_one_or_none.return_value = None
    session = MagicMock()
    session.execute = AsyncMock(return_value=inv_result)

    svc = InvitationService(
        session=session,
        audit=MagicMock(),
        tenant_id=uuid4(),
        actor_id=uuid4(),
    )

    with pytest.raises(NotFoundError):
        await svc.get(uuid4())
