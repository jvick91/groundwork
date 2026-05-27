"""
Auth0 app_metadata sync service (TASK-014C).

Mirrors Person state changes to Auth0 ``app_metadata`` so the Post-Login
Action can gate inactive users without making a synchronous backend call
during the login flow.

Contract:
  - ``sync_person_status()`` is called as a side effect inside the same DB
    transaction as the Person mutation. If Auth0 is unreachable and all
    retries fail, ``Auth0ManagementError`` propagates up to the caller, which
    causes SQLAlchemy to roll back the transaction — Auth0 and the DB are
    never left inconsistent.
  - Non-authenticating personas (``auth_subject=None``, e.g. client or
    guardian records) are skipped silently.

Staleness window (documented in docs/auth0-post-login-actions.md):
  - A successful deactivation takes effect immediately on next login.
  - Existing access tokens remain valid until their TTL expires (≤ 15 min).
  - Immediate revocation requires TASK-014J (force-kill).
"""

from __future__ import annotations

from app.core.logger import get_logger
from app.services.auth0_management_service import Auth0ManagementService

logger = get_logger(__name__)


class Auth0SyncService:
    """Thin orchestration layer between PersonService and Auth0ManagementService.

    Keeping this as a separate class (rather than calling Auth0ManagementService
    directly from PersonService) makes the dependency explicit and easy to swap
    out in tests.
    """

    def __init__(self, management: Auth0ManagementService) -> None:
        self._management = management

    async def sync_person_status(
        self,
        auth_subject: str | None,
        *,
        is_active: bool,
    ) -> None:
        """Mirror a Person's active/inactive status to Auth0 app_metadata.

        Args:
            auth_subject: The Auth0 subject (``auth0|...``) from ``Person.auth_subject``.
                          Pass ``None`` for non-authenticating personas — the call
                          is silently skipped.
            is_active:    The new status to push to ``app_metadata.is_active``.

        Raises:
            Auth0ManagementError: If the Management API returns a permanent error
                                  or all retry attempts are exhausted. The caller
                                  must let this propagate so the DB transaction
                                  rolls back.
        """
        if auth_subject is None:
            return

        logger.info(
            "auth0_sync_person_status",
            auth_subject=auth_subject,
            is_active=is_active,
        )
        await self._management.update_app_metadata(
            auth_subject,
            {"is_active": is_active},
        )
