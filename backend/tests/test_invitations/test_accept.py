"""
Invitation accept tests (TASK-014G).

Named acceptance-criteria tests:
  - test_accept_with_valid_nonce_and_jwt_writes_auth_subject_and_person_role
  - test_accept_with_unknown_nonce_returns_410
  - test_accept_with_expired_nonce_returns_410
  - test_accept_with_revoked_nonce_returns_410
  - test_accept_with_already_accepted_nonce_returns_410
  - test_accept_provider_creates_entity_instance
  - test_accept_cross_org_existing_person_creates_only_person_role
  - test_accept_cross_org_unknown_auth_subject_returns_409
  - test_accept_org_id_mismatch_returns_422
  - test_accept_increments_permissions_version
  - test_accept_writes_audit_log

Tests exercise the service layer directly, mocking the AsyncSession.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import ConflictError, DomainValidationError, GoneError
from app.enums.identity import InvitationState, InvitationType
from app.models.compliance import AuditLog
from app.models.eav import EntityInstance, Organization
from app.models.identity import Invitation, Person, PersonRole, Role
from app.services.invitation_service import InvitationAcceptResult, InvitationService

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def make_pending_invitation(
    *,
    type: InvitationType = InvitationType.ADMIN,
    org_id: object | None = None,
    nonce: str = "valid-nonce",
    planned_role_slug: str = "admin",
    first_name: str = "Alice",
    last_name: str = "Invitee",
    email: str = "alice@example.com",
    planned_entity_instance_id: object | None = None,
    planned_entity_instance_payload: dict | None = None,
) -> MagicMock:
    inv = MagicMock(spec=Invitation)
    inv.id = uuid4()
    inv.organization_id = org_id or uuid4()
    inv.type = type
    inv.nonce = nonce
    inv.state = InvitationState.PENDING
    inv.expires_at = datetime.now(tz=UTC) + timedelta(days=7)
    inv.planned_role_slug = planned_role_slug
    inv.first_name = first_name
    inv.last_name = last_name
    inv.email = email
    inv.created_by_person_id = uuid4()
    inv.planned_entity_instance_id = planned_entity_instance_id
    inv.planned_entity_instance_payload = planned_entity_instance_payload
    inv.accepted_at = None
    inv.updated_at = None
    return inv


def make_org(auth_provider_org_id: str | None = "auth0org_test") -> MagicMock:
    org = MagicMock(spec=Organization)
    org.id = uuid4()
    org.auth_provider_org_id = auth_provider_org_id
    return org


def make_role(slug: str = "admin") -> MagicMock:
    role = MagicMock(spec=Role)
    role.id = uuid4()
    role.slug = slug
    role.organization_id = None
    return role


def make_person(
    *,
    auth_subject: str = "auth0|existing_user",
    permissions_version: int = 0,
) -> MagicMock:
    person = MagicMock(spec=Person)
    person.id = uuid4()
    person.auth_subject = auth_subject
    person.permissions_version = permissions_version
    person.deleted_at = None
    return person


def _scalar(value: object) -> MagicMock:
    """Wrap a value in a fake execute result."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def make_session(side_effects: list) -> MagicMock:
    """Return a mocked AsyncSession with pre-configured execute side effects."""
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock(side_effect=side_effects)
    return session


# ---------------------------------------------------------------------------
# test_accept_with_valid_nonce_and_jwt_writes_auth_subject_and_person_role
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accept_with_valid_nonce_and_jwt_writes_auth_subject_and_person_role() -> None:
    """Happy-path admin invite: Person is created with auth_subject, PersonRole created."""
    org = make_org()
    inv = make_pending_invitation(type=InvitationType.ADMIN, org_id=org.id)
    role = make_role("admin")

    session = make_session([_scalar(inv), _scalar(org), _scalar(role)])

    result = await InvitationService.accept_invitation(
        session=session,
        nonce="valid-nonce",
        auth_subject="auth0|new_user",
        jwt_org_id="auth0org_test",
    )

    assert isinstance(result, InvitationAcceptResult)
    # Verify Person was added to the session with correct auth_subject
    add_calls = [c.args[0] for c in session.add.call_args_list]
    persons = [o for o in add_calls if isinstance(o, Person)]
    assert len(persons) == 1
    assert persons[0].auth_subject == "auth0|new_user"
    assert persons[0].email == inv.email

    # PersonRole was added
    person_roles = [o for o in add_calls if isinstance(o, PersonRole)]
    assert len(person_roles) == 1
    assert person_roles[0].organization_id == inv.organization_id
    assert person_roles[0].role_id == role.id

    # Invitation transitioned to accepted
    assert inv.state == InvitationState.ACCEPTED
    assert inv.accepted_at is not None


# ---------------------------------------------------------------------------
# test_accept_with_unknown_nonce_returns_410
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accept_with_unknown_nonce_returns_410() -> None:
    """Nonce not found → GoneError."""
    session = make_session([_scalar(None)])

    with pytest.raises(GoneError):
        await InvitationService.accept_invitation(
            session=session,
            nonce="unknown-nonce",
            auth_subject="auth0|user",
            jwt_org_id="auth0org_test",
        )


# ---------------------------------------------------------------------------
# test_accept_with_expired_nonce_returns_410
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accept_with_expired_nonce_returns_410() -> None:
    """TTL exceeded → GoneError (invitation is PENDING but past expires_at)."""
    inv = make_pending_invitation()
    inv.expires_at = datetime.now(tz=UTC) - timedelta(seconds=1)  # already expired

    session = make_session([_scalar(inv)])

    with pytest.raises(GoneError):
        await InvitationService.accept_invitation(
            session=session,
            nonce=inv.nonce,
            auth_subject="auth0|user",
            jwt_org_id="auth0org_test",
        )


# ---------------------------------------------------------------------------
# test_accept_with_revoked_nonce_returns_410
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accept_with_revoked_nonce_returns_410() -> None:
    """Revoked invitation → GoneError."""
    inv = make_pending_invitation()
    inv.state = InvitationState.REVOKED

    session = make_session([_scalar(inv)])

    with pytest.raises(GoneError):
        await InvitationService.accept_invitation(
            session=session,
            nonce=inv.nonce,
            auth_subject="auth0|user",
            jwt_org_id="auth0org_test",
        )


# ---------------------------------------------------------------------------
# test_accept_with_already_accepted_nonce_returns_410
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accept_with_already_accepted_nonce_returns_410() -> None:
    """Already-accepted invitation → GoneError."""
    inv = make_pending_invitation()
    inv.state = InvitationState.ACCEPTED

    session = make_session([_scalar(inv)])

    with pytest.raises(GoneError):
        await InvitationService.accept_invitation(
            session=session,
            nonce=inv.nonce,
            auth_subject="auth0|user",
            jwt_org_id="auth0org_test",
        )


# ---------------------------------------------------------------------------
# test_accept_provider_creates_entity_instance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accept_provider_creates_entity_instance() -> None:
    """Type-1 (provider) invite with payload → EntityInstance is created."""
    org = make_org()
    entity_type_id = uuid4()
    inv = make_pending_invitation(
        type=InvitationType.PROVIDER,
        org_id=org.id,
        planned_role_slug="provider",
        planned_entity_instance_payload={"entity_type_id": str(entity_type_id)},
    )
    role = make_role("provider")

    # execute calls: inv, org, role (Person + EntityInstance added via session.add)
    session = make_session([_scalar(inv), _scalar(org), _scalar(role)])

    result = await InvitationService.accept_invitation(
        session=session,
        nonce=inv.nonce,
        auth_subject="auth0|provider_user",
        jwt_org_id="auth0org_test",
    )

    add_calls = [c.args[0] for c in session.add.call_args_list]
    entity_instances = [o for o in add_calls if isinstance(o, EntityInstance)]
    assert len(entity_instances) == 1
    assert entity_instances[0].organization_id == inv.organization_id
    assert entity_instances[0].entity_type_id == entity_type_id

    person_roles = [o for o in add_calls if isinstance(o, PersonRole)]
    assert len(person_roles) == 1
    assert isinstance(result, InvitationAcceptResult)


# ---------------------------------------------------------------------------
# test_accept_cross_org_existing_person_creates_only_person_role
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accept_cross_org_existing_person_creates_only_person_role() -> None:
    """Type-4 (cross_org) invite: existing Person is reused, no new Person created."""
    org = make_org()
    existing_person = make_person(auth_subject="auth0|existing_user")
    inv = make_pending_invitation(
        type=InvitationType.CROSS_ORG,
        org_id=org.id,
    )
    role = make_role("admin")

    # execute: inv, org, existing_person lookup, role
    session = make_session([_scalar(inv), _scalar(org), _scalar(existing_person), _scalar(role)])

    result = await InvitationService.accept_invitation(
        session=session,
        nonce=inv.nonce,
        auth_subject="auth0|existing_user",
        jwt_org_id="auth0org_test",
    )

    add_calls = [c.args[0] for c in session.add.call_args_list]
    # No new Person should have been added
    persons = [o for o in add_calls if isinstance(o, Person)]
    assert len(persons) == 0

    person_roles = [o for o in add_calls if isinstance(o, PersonRole)]
    assert len(person_roles) == 1
    assert person_roles[0].person_id == existing_person.id
    assert result.person is existing_person


# ---------------------------------------------------------------------------
# test_accept_cross_org_unknown_auth_subject_returns_409
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accept_cross_org_unknown_auth_subject_returns_409() -> None:
    """Type-4 invite but no Person row → ConflictError (409)."""
    org = make_org()
    inv = make_pending_invitation(type=InvitationType.CROSS_ORG, org_id=org.id)

    # Person lookup returns None
    session = make_session([_scalar(inv), _scalar(org), _scalar(None)])

    with pytest.raises(ConflictError):
        await InvitationService.accept_invitation(
            session=session,
            nonce=inv.nonce,
            auth_subject="auth0|nobody",
            jwt_org_id="auth0org_test",
        )


# ---------------------------------------------------------------------------
# test_accept_org_id_mismatch_returns_422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accept_org_id_mismatch_returns_422() -> None:
    """JWT org_id does not match invitation's Auth0 org → DomainValidationError (422)."""
    org = make_org(auth_provider_org_id="auth0org_correct")
    inv = make_pending_invitation(org_id=org.id)

    session = make_session([_scalar(inv), _scalar(org)])

    with pytest.raises(DomainValidationError):
        await InvitationService.accept_invitation(
            session=session,
            nonce=inv.nonce,
            auth_subject="auth0|user",
            jwt_org_id="auth0org_WRONG",  # mismatch
        )


# ---------------------------------------------------------------------------
# test_accept_increments_permissions_version
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accept_increments_permissions_version() -> None:
    """Person.permissions_version is incremented inside the transaction (ADR-012)."""
    org = make_org()
    existing_person = make_person(auth_subject="auth0|versioned_user", permissions_version=3)
    inv = make_pending_invitation(type=InvitationType.CROSS_ORG, org_id=org.id)
    role = make_role("admin")

    session = make_session([_scalar(inv), _scalar(org), _scalar(existing_person), _scalar(role)])

    await InvitationService.accept_invitation(
        session=session,
        nonce=inv.nonce,
        auth_subject="auth0|versioned_user",
        jwt_org_id="auth0org_test",
    )

    assert existing_person.permissions_version == 4


# ---------------------------------------------------------------------------
# test_accept_writes_audit_log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accept_writes_audit_log() -> None:
    """An AuditLog row is added in the same session as the business mutation."""
    org = make_org()
    inv = make_pending_invitation(type=InvitationType.ADMIN, org_id=org.id)
    role = make_role("admin")

    session = make_session([_scalar(inv), _scalar(org), _scalar(role)])

    await InvitationService.accept_invitation(
        session=session,
        nonce=inv.nonce,
        auth_subject="auth0|audit_user",
        jwt_org_id="auth0org_test",
    )

    add_calls = [c.args[0] for c in session.add.call_args_list]
    audit_rows = [o for o in add_calls if isinstance(o, AuditLog)]
    assert len(audit_rows) == 1
    assert audit_rows[0].action == "invitation.accepted"
    assert audit_rows[0].resource_type == "Invitation"
    assert audit_rows[0].resource_id == inv.id
    assert audit_rows[0].organization_id == inv.organization_id
