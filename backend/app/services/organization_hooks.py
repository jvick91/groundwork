"""
Hook registry for the ``on_organization_created`` extension point.

Later tasks subscribe here to seed per-org reference data in the same
transaction as the Organization insert (TASK-029 for DocumentType/ConsentType,
TASK-032 for FormTemplate seed). If any hook raises, the Organization insert,
audit write, and all prior hook writes roll back atomically — the ``get_db``
dependency owns the transaction boundary.

Usage
-----
Register during module import (e.g. in a seed module's ``__init__.py``):

    from app.services.organization_hooks import register_on_create_hook

    async def _seed_document_types(db: AsyncSession, org_id: UUID) -> None:
        ...

    register_on_create_hook(_seed_document_types)
"""

from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

_HookFn = Callable[[AsyncSession, UUID], Awaitable[None]]

_hooks: list[_HookFn] = []


def register_on_create_hook(fn: _HookFn) -> None:
    """Append ``fn`` to the list of callables invoked after an org is created."""
    _hooks.append(fn)


def clear_hooks() -> None:
    """Remove all registered hooks. Intended for use in tests only."""
    _hooks.clear()


async def on_organization_created(db: AsyncSession, org_id: UUID) -> None:
    """Invoke every registered hook in registration order.

    Runs inside the same database transaction as the Organization insert and
    audit write. Any exception propagates immediately, rolling back the entire
    transaction via ``get_db``.
    """
    for hook in _hooks:
        await hook(db, org_id)
