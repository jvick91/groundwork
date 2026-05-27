"""
Auth0 app_metadata sync tests (TASK-014C).

Covers:
  - Auth0SyncService.sync_person_status delegates to management service.
  - Sync is skipped for personas without an auth_subject.
  - Management API errors propagate (no swallowing).
  - PersonService.update() calls sync when is_active changes.
  - PersonService.update() does NOT call sync when is_active is unchanged.
  - PersonService.delete() always calls sync with is_active=False.
  - PersonService works without a sync service (auth0_sync=None).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio

from app.core.exceptions import Auth0ManagementError
from app.models.identity import Person
from app.schemas.identity import PersonUpdate
from app.services.auth0_management_service import Auth0ManagementService
from app.services.auth0_sync_service import Auth0SyncService
from app.services.identity_service import PersonService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_management_service(*, update_ok: bool = True) -> Auth0ManagementService:
    """Build a fully-mocked Auth0ManagementService."""
    svc = MagicMock(spec=Auth0ManagementService)
    if update_ok:
        svc.update_app_metadata = AsyncMock(return_value=None)
    else:
        svc.update_app_metadata = AsyncMock(
            side_effect=Auth0ManagementError("management error", status_code=502)
        )
    return svc


def make_sync_service(*, update_ok: bool = True) -> Auth0SyncService:
    management = make_management_service(update_ok=update_ok)
    return Auth0SyncService(management)


def make_person(
    *,
    is_active: bool = True,
    auth_subject: str | None = "auth0|abc123",
    deleted_at: datetime | None = None,
) -> Person:
    person = MagicMock(spec=Person)
    person.id = uuid4()
    person.auth_subject = auth_subject
    person.is_active = is_active
    person.deleted_at = deleted_at
    person.first_name = "Test"
    person.last_name = "User"
    person.email = "test@example.com"
    person.phone = None
    person.updated_at = None
    return person


def make_person_service(
    person: Person, *, auth0_sync: Auth0SyncService | None = None
) -> PersonService:
    """Build a PersonService with a mock session/audit and optional sync."""
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()

    # Wrap scalar result for _get_visible
    scalar_result = MagicMock()
    scalar_result.scalars.return_value.first.return_value = person
    session.execute.return_value = scalar_result

    audit = MagicMock()
    audit.write = AsyncMock()

    return PersonService(
        session=session,
        audit=audit,
        tenant_id=uuid4(),
        actor_id=uuid4(),
        auth0_sync=auth0_sync,
    )


# ---------------------------------------------------------------------------
# Auth0SyncService unit tests
# ---------------------------------------------------------------------------


class TestAuth0SyncService:
    @pytest.mark.asyncio
    async def test_sync_calls_update_app_metadata(self) -> None:
        management = make_management_service()
        svc = Auth0SyncService(management)

        await svc.sync_person_status("auth0|user1", is_active=False)

        management.update_app_metadata.assert_awaited_once_with(
            "auth0|user1", {"is_active": False}
        )

    @pytest.mark.asyncio
    async def test_sync_active_status(self) -> None:
        management = make_management_service()
        svc = Auth0SyncService(management)

        await svc.sync_person_status("auth0|user1", is_active=True)

        management.update_app_metadata.assert_awaited_once_with(
            "auth0|user1", {"is_active": True}
        )

    @pytest.mark.asyncio
    async def test_sync_skipped_when_auth_subject_is_none(self) -> None:
        """Non-authenticating personas have no Auth0 account — skip silently."""
        management = make_management_service()
        svc = Auth0SyncService(management)

        await svc.sync_person_status(None, is_active=False)

        management.update_app_metadata.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_management_error_propagates(self) -> None:
        """Management API failures must NOT be swallowed — caller must roll back."""
        svc = make_sync_service(update_ok=False)

        with pytest.raises(Auth0ManagementError):
            await svc.sync_person_status("auth0|user1", is_active=False)


# ---------------------------------------------------------------------------
# PersonService integration: update()
# ---------------------------------------------------------------------------


class TestPersonServiceUpdateSync:
    @pytest.mark.asyncio
    async def test_sync_called_when_is_active_changes_to_false(self) -> None:
        person = make_person(is_active=True, auth_subject="auth0|user1")
        sync = make_sync_service()
        sync.sync_person_status = AsyncMock()
        svc = make_person_service(person, auth0_sync=sync)

        await svc.update(person.id, PersonUpdate(is_active=False))

        sync.sync_person_status.assert_awaited_once_with("auth0|user1", is_active=False)

    @pytest.mark.asyncio
    async def test_sync_called_when_is_active_changes_to_true(self) -> None:
        person = make_person(is_active=False, auth_subject="auth0|user1")
        sync = make_sync_service()
        sync.sync_person_status = AsyncMock()
        svc = make_person_service(person, auth0_sync=sync)

        await svc.update(person.id, PersonUpdate(is_active=True))

        sync.sync_person_status.assert_awaited_once_with("auth0|user1", is_active=True)

    @pytest.mark.asyncio
    async def test_sync_not_called_when_is_active_unchanged(self) -> None:
        """Update that does not touch is_active must not trigger sync."""
        person = make_person(is_active=True, auth_subject="auth0|user1")
        sync = make_sync_service()
        sync.sync_person_status = AsyncMock()
        svc = make_person_service(person, auth0_sync=sync)

        await svc.update(person.id, PersonUpdate(first_name="New"))

        sync.sync_person_status.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sync_not_called_when_is_active_set_to_same_value(self) -> None:
        """Setting is_active to its current value must not trigger sync."""
        person = make_person(is_active=True, auth_subject="auth0|user1")
        sync = make_sync_service()
        sync.sync_person_status = AsyncMock()
        svc = make_person_service(person, auth0_sync=sync)

        await svc.update(person.id, PersonUpdate(is_active=True))

        sync.sync_person_status.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_management_error_surfaces_from_update(self) -> None:
        """Management API 502 must propagate so the caller can handle rollback."""
        person = make_person(is_active=True, auth_subject="auth0|user1")
        sync = make_sync_service(update_ok=False)
        svc = make_person_service(person, auth0_sync=sync)

        with pytest.raises(Auth0ManagementError):
            await svc.update(person.id, PersonUpdate(is_active=False))

    @pytest.mark.asyncio
    async def test_update_works_without_sync_service(self) -> None:
        """PersonService must operate normally when auth0_sync is None."""
        person = make_person(is_active=True)
        svc = make_person_service(person, auth0_sync=None)

        result = await svc.update(person.id, PersonUpdate(is_active=False))

        assert result is not None


# ---------------------------------------------------------------------------
# PersonService integration: delete()
# ---------------------------------------------------------------------------


class TestPersonServiceDeleteSync:
    @pytest.mark.asyncio
    async def test_sync_called_on_delete(self) -> None:
        person = make_person(is_active=True, auth_subject="auth0|user1")
        sync = make_sync_service()
        sync.sync_person_status = AsyncMock()
        svc = make_person_service(person, auth0_sync=sync)

        await svc.delete(person.id)

        sync.sync_person_status.assert_awaited_once_with("auth0|user1", is_active=False)

    @pytest.mark.asyncio
    async def test_sync_called_on_delete_for_already_inactive_person(self) -> None:
        """Soft-delete always syncs is_active=False regardless of prior state."""
        person = make_person(is_active=False, auth_subject="auth0|user1")
        sync = make_sync_service()
        sync.sync_person_status = AsyncMock()
        svc = make_person_service(person, auth0_sync=sync)

        await svc.delete(person.id)

        sync.sync_person_status.assert_awaited_once_with("auth0|user1", is_active=False)

    @pytest.mark.asyncio
    async def test_sync_skipped_on_delete_for_non_auth_person(self) -> None:
        """Personas without auth_subject are not in Auth0 — skip sync."""
        person = make_person(is_active=True, auth_subject=None)
        sync = make_sync_service()
        sync.sync_person_status = AsyncMock()
        svc = make_person_service(person, auth0_sync=sync)

        await svc.delete(person.id)

        sync.sync_person_status.assert_awaited_once_with(None, is_active=False)
        # Underlying management service should not be called
        # (sync_person_status handles the None check internally)

    @pytest.mark.asyncio
    async def test_management_error_surfaces_from_delete(self) -> None:
        person = make_person(is_active=True, auth_subject="auth0|user1")
        sync = make_sync_service(update_ok=False)
        svc = make_person_service(person, auth0_sync=sync)

        with pytest.raises(Auth0ManagementError):
            await svc.delete(person.id)

    @pytest.mark.asyncio
    async def test_delete_works_without_sync_service(self) -> None:
        person = make_person(is_active=True)
        svc = make_person_service(person, auth0_sync=None)

        # Should complete without raising
        await svc.delete(person.id)
