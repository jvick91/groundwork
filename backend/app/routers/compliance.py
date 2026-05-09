"""
Compliance domain router — AuditLog read endpoints (SPEC-006 §6).

GET /audit-log        — paginated list with filters
GET /audit-log/{id}   — single entry

Both endpoints require the ``audit.read`` permission (enforced once TASK-014
and TASK-015 wire up auth middleware and permission resolution).
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.exceptions import NotFoundError
from app.core.pagination import apply_date_range_filter, apply_exact_filter, paginate
from app.core.security import require_permission
from app.models.compliance import AuditLog
from app.schemas.pagination import PaginatedResponse, PaginationParams

router = APIRouter(prefix="/audit-log", tags=["compliance"])

_SORT_FIELDS = {
    "occurred_at": AuditLog.occurred_at,
}


# ---------------------------------------------------------------------------
# Response schema (inline — full Pydantic schemas come in TASK-008A)
# ---------------------------------------------------------------------------


def _serialize(entry: AuditLog) -> dict[str, Any]:
    return {
        "id": str(entry.id),
        "organization_id": str(entry.organization_id),
        "actor_person_id": str(entry.actor_person_id) if entry.actor_person_id else None,
        "action": entry.action,
        "resource_type": entry.resource_type,
        "resource_id": str(entry.resource_id),
        "previous_state": entry.previous_state,
        "next_state": entry.next_state,
        "ip_address": entry.ip_address,
        "user_agent": entry.user_agent,
        "outcome": entry.outcome,
        "occurred_at": entry.occurred_at.isoformat() if entry.occurred_at else None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
    dependencies=[require_permission("audit.read")],
    response_model=PaginatedResponse,
)
async def list_audit_log(
    params: PaginationParams = Depends(),
    actor_person_id: UUID | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    resource_id: UUID | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse:
    """Query audit log entries with optional filters (SPEC-006 §6)."""
    stmt = select(AuditLog)

    stmt = apply_exact_filter(stmt, AuditLog.actor_person_id, actor_person_id)
    stmt = apply_exact_filter(stmt, AuditLog.resource_type, resource_type)
    stmt = apply_exact_filter(stmt, AuditLog.resource_id, resource_id)
    stmt = apply_date_range_filter(stmt, AuditLog.occurred_at, date_from, date_to)

    items, meta = await paginate(
        db,
        stmt,
        params=params,
        sort_fields=_SORT_FIELDS,
        id_col=AuditLog.id,
    )

    return PaginatedResponse(data=[_serialize(e) for e in items], pagination=meta)


@router.get(
    "/{entry_id}",
    dependencies=[require_permission("audit.read")],
)
async def get_audit_log_entry(
    entry_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve a single audit log entry by ID (SPEC-006 §6)."""
    entry = await db.get(AuditLog, entry_id)
    if entry is None:
        raise NotFoundError("AuditLog", entry_id)
    return _serialize(entry)
