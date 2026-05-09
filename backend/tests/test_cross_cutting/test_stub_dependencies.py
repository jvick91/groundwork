"""
Stub dependency shape tests (TASK-008A).

While ``settings.auth_stub_enabled = True``, the auth dependencies must
short-circuit to a documented test identity rather than blocking the
request. These tests pin the **shape** of that identity so TASK-014/015
catch any drift the moment they swap the stub for real auth — the keys
asserted here are the contract the rest of the app will rely on.
"""

from __future__ import annotations

from uuid import UUID

import pytest

from app.core.config import settings
from app.core.security import (
    AuthContext,
    current_org,
    current_person,
    get_auth_context,
    require_permission,
)

pytestmark = pytest.mark.asyncio


async def test_get_auth_context_returns_stub_identity_while_flag_on() -> None:
    """The stub identity is deterministic and points at dev-seeded rows."""
    assert settings.auth_stub_enabled is True
    auth = await get_auth_context()
    assert isinstance(auth, AuthContext)
    assert isinstance(auth.person_id, UUID)
    assert isinstance(auth.organization_id, UUID)
    assert auth.auth_subject.startswith("auth0|")


async def test_current_person_shape() -> None:
    """current_person returns a dict with id, email, is_active."""
    auth = await get_auth_context()
    person = await current_person(auth)
    assert set(person.keys()) >= {"id", "email", "is_active"}
    assert isinstance(person["id"], UUID)
    assert isinstance(person["email"], str) and "@" in person["email"]
    assert person["is_active"] is True


async def test_current_org_shape() -> None:
    """current_org returns a dict with id, name, timezone."""
    auth = await get_auth_context()
    org = await current_org(auth)
    assert set(org.keys()) >= {"id", "name", "timezone"}
    assert isinstance(org["id"], UUID)
    assert isinstance(org["name"], str) and org["name"]
    assert isinstance(org["timezone"], str) and org["timezone"]


async def test_require_permission_allow_lists_while_flag_on() -> None:
    """While the stub flag is on, every permission check passes regardless of slug."""
    # Extract the underlying function from the Depends wrapper for direct invocation.
    dep = require_permission("nonexistent.permission")
    check_callable = dep.dependency
    assert check_callable is not None

    auth = await get_auth_context()
    result = await check_callable(auth=auth)
    assert isinstance(result, AuthContext)


async def test_require_permission_blocks_when_flag_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative-path: with the stub disabled, a missing permission raises 403.

    This is the path TASK-014/015 will leave behind when they ship; the
    test pins the rejection contract so future edits do not silently
    weaken authorization.
    """
    from fastapi import HTTPException

    monkeypatch.setattr(settings, "auth_stub_enabled", False)

    # When the flag is off, get_auth_context raises 501 (no real auth yet).
    # We construct an AuthContext directly to exercise the permission check.
    from uuid import uuid4

    auth = AuthContext(
        person_id=uuid4(),
        auth_subject="auth0|real-user",
        organization_id=uuid4(),
        permissions=set(),  # no permissions granted
    )

    dep = require_permission("organization.delete")
    check_callable = dep.dependency
    assert check_callable is not None

    with pytest.raises(HTTPException) as exc_info:
        await check_callable(auth=auth)
    assert exc_info.value.status_code == 403
