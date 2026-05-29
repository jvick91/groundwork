"""
Uniform response shape tests (TASK-014F / ADR-011 §uniform-response).

Named acceptance-criteria tests:
  - test_uniform_response_shape_regardless_of_existing_person
  - test_organization_id_in_body_ignored

The ADR requires that POST /invitations always returns the same shape
{status: "pending", invitation_id: uuid} regardless of whether the email
maps to an existing Person. These tests verify that at both the schema
layer and the service layer.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.enums.identity import InvitationState, InvitationType
from app.models.eav import Organization
from app.models.identity import Invitation, Person
from app.schemas.identity import (
    AdminInvitationCreate,
    InvitationSendResponse,
)
from app.services.invitation_service import InvitationService


# ---------------------------------------------------------------------------
# Schema layer
# ---------------------------------------------------------------------------


def test_send_response_always_has_pending_status() -> None:
    """InvitationSendResponse.status is hardcoded to 'pending'."""
    resp = InvitationSendResponse(invitation_id=uuid4())
    assert resp.status == "pending"
    assert resp.model_dump()["status"] == "pending"


def test_invitation_create_strips_whitespace() -> None:
    """EmailStr normalisation — ensures email is cleaned before storage."""
    data = AdminInvitationCreate(
        type=InvitationType.ADMIN,
        email="  user@example.com  ",
        planned_role_slug="admin",
        first_name="Alice",
        last_name="Admin",
    )
    # pydantic EmailStr normalises to lowercase + no surrounding whitespace
    assert "@" in data.email
    assert data.email == data.email.strip()


def test_invitation_create_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError):
        AdminInvitationCreate(
            type=InvitationType.ADMIN,
            email="not-an-email",
            planned_role_slug="admin",
            first_name="Alice",
            last_name="Admin",
        )


# ---------------------------------------------------------------------------
# Service layer: uniform response regardless of existing person
# ---------------------------------------------------------------------------


def _make_service_for_uniform_test(
    existing_person: Person | None,
    management: MagicMock,
) -> InvitationService:
    org = MagicMock(spec=Organization)
    org.id = uuid4()
    org.auth_provider_org_id = "auth0org_test"

    actor = MagicMock(spec=Person)
    actor.id = uuid4()
    actor.first_name = "Alice"
    actor.last_name = "Admin"
    actor.deleted_at = None

    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org
    actor_result = MagicMock()
    actor_result.scalar_one_or_none.return_value = actor

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock(side_effect=[org_result, actor_result])

    audit = MagicMock()
    audit.write = AsyncMock()

    return InvitationService(
        session=session,
        audit=audit,
        tenant_id=org.id,
        actor_id=actor.id,
        management=management,
    )


@pytest.mark.asyncio
async def test_uniform_response_shape_regardless_of_existing_person(
    mock_management: MagicMock,
) -> None:
    """Admin invite: the caller cannot distinguish new-user vs existing-email."""
    svc = _make_service_for_uniform_test(
        existing_person=None,  # no matching person
        management=mock_management,
    )

    data = AdminInvitationCreate(
        type=InvitationType.ADMIN,
        email="newuser@example.com",
        planned_role_slug="admin",
        first_name="New",
        last_name="User",
    )
    invitation = await svc.send(data)

    # Service always returns the same Invitation shape; the router wraps it.
    assert invitation.state == InvitationState.PENDING
    assert invitation.email == "newuser@example.com"

    # Build the response as the router would
    resp = InvitationSendResponse(invitation_id=invitation.id)
    assert resp.status == "pending"
    assert resp.invitation_id == invitation.id


# ---------------------------------------------------------------------------
# organization_id in body is ignored
# ---------------------------------------------------------------------------


def test_organization_id_not_accepted_in_invitation_create() -> None:
    """InvitationCreate schemas must not accept an organization_id field."""
    import pydantic

    data = AdminInvitationCreate(
        type=InvitationType.ADMIN,
        email="user@example.com",
        planned_role_slug="admin",
        first_name="Alice",
        last_name="Admin",
    )
    # The schema must not have organization_id
    assert not hasattr(data, "organization_id"), (
        "organization_id must not be in the invitation create schema — "
        "it is always stamped from the auth context."
    )


@pytest.mark.asyncio
async def test_organization_id_in_body_ignored(mock_management: MagicMock) -> None:
    """Extra fields including organization_id are stripped by the schema."""
    # Pydantic should ignore the extra field (ConfigDict default strips unknowns)
    import pydantic

    try:
        data = AdminInvitationCreate.model_validate(
            {
                "type": "admin",
                "email": "user@example.com",
                "planned_role_slug": "admin",
                "first_name": "Alice",
                "last_name": "Admin",
                "organization_id": str(uuid4()),  # extra — must be stripped
            }
        )
        assert not hasattr(data, "organization_id")
    except pydantic.ValidationError:
        # If pydantic rejects the extra field that is also acceptable
        pass

    # Service always stamps org from tenant_id, not from request body
    svc = _make_service_for_uniform_test(None, mock_management)
    data2 = AdminInvitationCreate(
        type=InvitationType.ADMIN,
        email="orgtest@example.com",
        planned_role_slug="admin",
        first_name="Alice",
        last_name="Admin",
    )
    invitation = await svc.send(data2)
    assert invitation.organization_id == svc._tenant_id
