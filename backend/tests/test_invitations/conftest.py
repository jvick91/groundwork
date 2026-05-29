"""
Shared fixtures for invitation tests.

All Auth0 calls are mocked — no real network traffic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.auth0_management_service import Auth0ManagementService


@pytest.fixture
def mock_management() -> MagicMock:
    """Return a fully-mocked Auth0ManagementService."""
    mock = MagicMock(spec=Auth0ManagementService)
    mock.create_organization_invitation = AsyncMock(
        return_value={"id": "auth0inv_abc", "invitation_url": "https://auth0.com/inv/test"}
    )
    mock.revoke_organization_invitation = AsyncMock(return_value=None)
    mock.add_organization_member = AsyncMock(return_value=None)
    return mock
