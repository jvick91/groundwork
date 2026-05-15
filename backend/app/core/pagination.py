"""
Cursor-based pagination utility (SPEC-007 §5 and §6).

Public surface
--------------
encode_cursor / decode_cursor
    Opaque Base64-JSON cursor that encodes (sort_value, record_id).

paginate(session, stmt, *, params, sort_fields, id_col)
    Applies cursor WHERE clause, ORDER BY, and LIMIT+1 probe to a
    SQLAlchemy SELECT, then returns (items, PaginationMeta).
    Raises BadRequestError if params.sort is not in sort_fields.

Filter helpers  (SPEC-007 §6.1)
    apply_exact_filter      — WHERE col = value
    apply_in_filter         — WHERE col IN (...) from comma-separated string
    apply_date_range_filter — WHERE col >= date_from AND col <= date_to
    apply_text_search       — WHERE col ILIKE '%q%'

Usage pattern in a domain repository (ADR-009):
    from sqlalchemy import select
    from app.core.pagination import paginate
    from app.models.eav import Organization
    from app.schemas.pagination import PaginationParams

    class OrganizationRepository:
        async def list_for_page(self, params: PaginationParams):
            stmt = select(Organization).where(Organization.deleted_at.is_(None))
            return await paginate(
                self._session, stmt, params=params,
                sort_fields={"created_at": Organization.created_at,
                             "name": Organization.name},
                id_col=Organization.id,
            )
"""

import base64
import json
from datetime import date, datetime
from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import Date, DateTime, Select, asc, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.exceptions import BadRequestError
from app.schemas.pagination import PaginationMeta, PaginationParams, SortDir

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Cursor encode / decode
# ---------------------------------------------------------------------------


def encode_cursor(sort_value: Any, record_id: UUID | str) -> str:
    """Encode a keyset cursor as a URL-safe Base64 JSON string.

    The payload is ``{"v": <sort_value>, "id": <record_id>}``.
    Datetime and date values are stored as ISO 8601 strings.
    The format is opaque to API clients and may change between versions.
    """
    if isinstance(sort_value, datetime | date):
        v = sort_value.isoformat()
    elif isinstance(sort_value, UUID):
        v = str(sort_value)
    else:
        v = sort_value

    payload = {"v": v, "id": str(record_id)}
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()


def decode_cursor(cursor: str) -> dict[str, Any]:
    """Decode a cursor string.

    Raises BadRequestError on malformed or tampered input so the caller
    does not need to handle raw decode exceptions.
    """
    try:
        # Add padding in case the encoded string lost trailing '='
        padded = cursor + "==" * (4 - len(cursor) % 4)
        data: dict[str, Any] = json.loads(base64.urlsafe_b64decode(padded))
        if "v" not in data or "id" not in data:
            raise ValueError("missing required cursor keys")
        return data
    except Exception as exc:
        raise BadRequestError("Invalid or expired pagination cursor.") from exc


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _coerce_cursor_value(raw: Any, sort_col: InstrumentedAttribute[Any]) -> Any:
    """Convert a raw JSON cursor value to the Python type that SQLAlchemy expects."""
    try:
        col_type = sort_col.property.columns[0].type
        if isinstance(col_type, DateTime) and isinstance(raw, str):
            return datetime.fromisoformat(raw)
        if isinstance(col_type, Date) and isinstance(raw, str):
            return date.fromisoformat(raw)
    except Exception:
        pass
    return raw


# ---------------------------------------------------------------------------
# Core pagination function
# ---------------------------------------------------------------------------


async def paginate(
    session: AsyncSession,
    stmt: Select[Any],
    *,
    params: PaginationParams,
    sort_fields: dict[str, InstrumentedAttribute[Any]],
    id_col: InstrumentedAttribute[Any],
) -> tuple[list[Any], PaginationMeta]:
    """Apply cursor conditions, ordering, and limit to a SQLAlchemy SELECT.

    Parameters
    ----------
    session:
        Active AsyncSession provided by the FastAPI dependency.
    stmt:
        A ``select()`` statement with any domain-specific WHERE clauses
        already applied (org scope, soft-delete filter, etc.).
    params:
        Parsed query parameters from ``PaginationParams``.
    sort_fields:
        Dict mapping allowed sort field names to ORM column attributes.
        Acts as both an allow-list and a field → column mapping.
        Example: ``{"created_at": Organization.created_at, "name": Organization.name}``
    id_col:
        The primary key column used as a stable tiebreaker.

    Returns
    -------
    (items, PaginationMeta)
        ``items`` contains at most ``params.limit`` rows.
        ``PaginationMeta`` is ready to embed in a ``PaginatedResponse``.

    Raises
    ------
    BadRequestError
        If ``params.sort`` is not in ``sort_fields``, or if the cursor is malformed.
    """
    if params.sort not in sort_fields:
        raise BadRequestError(
            f"Cannot sort by '{params.sort}'. Allowed fields: {sorted(sort_fields)}."
        )

    sort_col = sort_fields[params.sort]
    direction = desc if params.sort_dir == SortDir.DESC else asc

    # Apply cursor keyset condition for pages beyond the first
    if params.cursor:
        cursor_data = decode_cursor(params.cursor)
        cursor_v = _coerce_cursor_value(cursor_data["v"], sort_col)
        cursor_id = cursor_data["id"]

        if params.sort_dir == SortDir.DESC:
            # Rows before the cursor in descending order
            stmt = stmt.where(
                (sort_col < cursor_v) | ((sort_col == cursor_v) & (id_col < cursor_id))
            )
        else:
            # Rows after the cursor in ascending order
            stmt = stmt.where(
                (sort_col > cursor_v) | ((sort_col == cursor_v) & (id_col > cursor_id))
            )

    # Stable ordering: (sort_col, id) ensures no ambiguity on ties
    stmt = stmt.order_by(direction(sort_col), direction(id_col))

    # Fetch limit+1 to detect whether a next page exists
    stmt = stmt.limit(params.limit + 1)

    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    has_next = len(rows) > params.limit
    items = rows[: params.limit]

    # Build next cursor from the last item on this page
    next_cursor: str | None = None
    if has_next and items:
        last = items[-1]
        next_cursor = encode_cursor(getattr(last, params.sort), last.id)

    # Build previous cursor from the first item on this page
    # (allows the caller to navigate backwards)
    previous_cursor: str | None = None
    if params.cursor and items:
        first = items[0]
        previous_cursor = encode_cursor(getattr(first, params.sort), first.id)

    return items, PaginationMeta(
        next_cursor=next_cursor,
        previous_cursor=previous_cursor,
        has_next=has_next,
        has_previous=params.cursor is not None,
        limit=params.limit,
    )


# ---------------------------------------------------------------------------
# Filter helpers  (SPEC-007 §6.1)
# ---------------------------------------------------------------------------


def apply_exact_filter(
    stmt: Select[Any], col: InstrumentedAttribute[Any], value: Any
) -> Select[Any]:
    """WHERE col = value.  No-op when value is None."""
    if value is not None:
        return stmt.where(col == value)
    return stmt


def apply_in_filter(
    stmt: Select[Any], col: InstrumentedAttribute[Any], value: str | None
) -> Select[Any]:
    """WHERE col IN (...) parsed from a comma-separated query param.

    Example: ``?status=DRAFT,SENT`` → ``WHERE status IN ('DRAFT', 'SENT')``
    No-op when value is None or empty.
    """
    if value:
        values = [v.strip() for v in value.split(",") if v.strip()]
        if values:
            return stmt.where(col.in_(values))
    return stmt


def apply_date_range_filter(
    stmt: Select[Any],
    col: InstrumentedAttribute[Any],
    date_from: date | datetime | None,
    date_to: date | datetime | None,
) -> Select[Any]:
    """WHERE col >= date_from AND col <= date_to.

    Each bound is optional.  Both bounds are inclusive.
    """
    if date_from is not None:
        stmt = stmt.where(col >= date_from)
    if date_to is not None:
        stmt = stmt.where(col <= date_to)
    return stmt


def apply_text_search(
    stmt: Select[Any], col: InstrumentedAttribute[Any], q: str | None
) -> Select[Any]:
    """WHERE col ILIKE '%q%'.  No-op when q is None or empty."""
    if q:
        return stmt.where(col.ilike(f"%{q}%"))
    return stmt
