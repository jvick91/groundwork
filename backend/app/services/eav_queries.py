"""
JSONB aggregation query builder for EntityInstance list views (ADR-004).

This module owns the canonical three-table join that collapses
EntityInstance → AttributeValue → EntityAttribute into a single
PostgreSQL query using ``jsonb_object_agg``. The result is one row per
EntityInstance with an ``attributes`` JSONB object containing all attribute
name → value pairs.

Canonical SQL (ADR-004 §Decision):

    SELECT ei.*, COALESCE(
             jsonb_object_agg(ea.name, av.value)
               FILTER (WHERE ea.name IS NOT NULL),
             '{}'::jsonb
           ) AS attributes
    FROM entity_instances ei
    LEFT JOIN attribute_values av ON av.entity_instance_id = ei.id
    LEFT JOIN entity_attributes ea ON ea.id = av.entity_attribute_id
    WHERE ei.organization_id = :org_id
      AND ei.entity_type_id  = :type_id
      AND ei.deleted_at      IS NULL
    GROUP BY ei.id
    ORDER BY ei.created_at DESC, ei.id DESC
    LIMIT :limit;

Cursor pagination is implemented directly here because the generic
``paginate()`` helper uses ``result.scalars()`` which does not handle
multi-column selects containing aggregate functions. The pagination logic
mirrors ``pagination.paginate()`` exactly so callers see the same
``PaginationMeta`` shape.

Public surface
--------------
``list_instances_jsonb(session, *, org_id, entity_type_id, params)``
    Returns ``(list[(EntityInstance, attributes_dict)], PaginationMeta)``.
    The caller maps the tuples to whatever response shape it needs.
    No imports from ``entity_instance_service`` — zero circular dependency.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import asc, desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import decode_cursor, encode_cursor
from app.models.eav import AttributeValue, EntityAttribute, EntityInstance
from app.schemas.pagination import PaginationMeta, PaginationParams, SortDir

# Columns supported for cursor-based sorting on the aggregated list.
_SORT_FIELDS: dict[str, Any] = {
    "created_at": EntityInstance.created_at,
    "updated_at": EntityInstance.updated_at,
}


async def list_instances_jsonb(
    session: AsyncSession,
    *,
    org_id: UUID,
    entity_type_id: UUID,
    params: PaginationParams,
) -> tuple[list[tuple[EntityInstance, dict[str, str | None]]], PaginationMeta]:
    """Run the canonical JSONB aggregation query and return paginated results.

    Parameters
    ----------
    session:
        Active async session (provided by the FastAPI dependency).
    org_id:
        Tenant filter — only instances belonging to this org are returned.
    entity_type_id:
        Type filter — only instances of this EntityType are returned.
    params:
        Cursor pagination parameters from the request query string.

    Returns
    -------
    (rows, meta)
        ``rows`` is a list of ``(EntityInstance, attributes)`` tuples where
        ``attributes`` is a ``dict[str, str | None]`` keyed by attribute name.
        ``meta`` is the standard ``PaginationMeta`` ready for a
        ``PaginatedResponse``.

    Raises
    ------
    BadRequestError
        If ``params.sort`` is not one of the supported sort fields.
    """
    from app.core.exceptions import BadRequestError

    if params.sort not in _SORT_FIELDS:
        raise BadRequestError(
            f"Cannot sort by '{params.sort}'. "
            f"Allowed fields: {sorted(_SORT_FIELDS)}."
        )

    sort_col = _SORT_FIELDS[params.sort]
    direction = desc if params.sort_dir == SortDir.DESC else asc

    # Build the JSONB aggregation expression (ADR-004 canonical pattern).
    attributes_agg = func.coalesce(
        func.jsonb_object_agg(
            EntityAttribute.name,
            AttributeValue.value,
        ).filter(EntityAttribute.name.isnot(None)),
        text("'{}'::jsonb"),
    ).label("attributes")

    stmt = (
        select(EntityInstance, attributes_agg)
        .join(
            AttributeValue,
            AttributeValue.entity_instance_id == EntityInstance.id,
            isouter=True,
        )
        .join(
            EntityAttribute,
            EntityAttribute.id == AttributeValue.entity_attribute_id,
            isouter=True,
        )
        .where(
            EntityInstance.organization_id == org_id,
            EntityInstance.entity_type_id == entity_type_id,
            EntityInstance.deleted_at.is_(None),
        )
        .group_by(EntityInstance.id)
    )

    # Apply cursor keyset condition (mirrors pagination.paginate logic).
    if params.cursor:
        cursor_data = decode_cursor(params.cursor)
        raw_v = cursor_data["v"]
        cursor_v: datetime | str = (
            datetime.fromisoformat(raw_v) if isinstance(raw_v, str) else raw_v
        )
        cursor_id = cursor_data["id"]

        if params.sort_dir == SortDir.DESC:
            stmt = stmt.where(
                (sort_col < cursor_v)
                | ((sort_col == cursor_v) & (EntityInstance.id < cursor_id))
            )
        else:
            stmt = stmt.where(
                (sort_col > cursor_v)
                | ((sort_col == cursor_v) & (EntityInstance.id > cursor_id))
            )

    # Stable ordering: (sort_col DESC, id DESC) matches the naive query.
    stmt = stmt.order_by(direction(sort_col), direction(EntityInstance.id))
    stmt = stmt.limit(params.limit + 1)

    result = await session.execute(stmt)
    raw_rows = result.all()

    has_next = len(raw_rows) > params.limit
    page_rows = raw_rows[: params.limit]

    # Map raw DB rows to typed (EntityInstance, attributes) tuples.
    items: list[tuple[EntityInstance, dict[str, str | None]]] = [
        (row[0], dict(row[1]) if row[1] else {})
        for row in page_rows
    ]

    # Build cursors from the first / last items on this page.
    next_cursor: str | None = None
    if has_next and page_rows:
        last_inst: EntityInstance = page_rows[-1][0]
        next_cursor = encode_cursor(getattr(last_inst, params.sort), last_inst.id)

    previous_cursor: str | None = None
    if params.cursor and page_rows:
        first_inst: EntityInstance = page_rows[0][0]
        previous_cursor = encode_cursor(getattr(first_inst, params.sort), first_inst.id)

    return items, PaginationMeta(
        next_cursor=next_cursor,
        previous_cursor=previous_cursor,
        has_next=has_next,
        has_previous=params.cursor is not None,
        limit=params.limit,
    )
