"""
Tests for the cursor pagination utility (SPEC-007 §5, §6).

Structure
---------
Part 1 — Unit tests (no DB, no async)
    Cursor encode/decode round-trips, malformed input, PaginationParams validation.

Part 2 — Integration tests (real PostgreSQL via db_session fixture)
    paginate() correctness: first page, next/previous cursors, has_next flag,
    sort field allow-list enforcement, and stability under concurrent inserts.
"""

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError
from app.models.models import Organization
from app.schemas.schemas import PaginationParams, SortDir
from app.utils.pagination import (
    apply_date_range_filter,
    apply_exact_filter,
    apply_in_filter,
    apply_text_search,
    decode_cursor,
    encode_cursor,
    paginate,
)


# ===========================================================================
# Part 1 — Unit tests
# ===========================================================================

class TestEncodeDecode:
    def test_roundtrip_string_sort_value(self):
        record_id = uuid.uuid4()
        cursor = encode_cursor("some_value", record_id)
        data = decode_cursor(cursor)
        assert data["v"] == "some_value"
        assert data["id"] == str(record_id)

    def test_roundtrip_datetime_sort_value(self):
        record_id = uuid.uuid4()
        ts = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
        cursor = encode_cursor(ts, record_id)
        data = decode_cursor(cursor)
        assert data["v"] == ts.isoformat()
        assert data["id"] == str(record_id)

    def test_roundtrip_uuid_sort_value(self):
        record_id = uuid.uuid4()
        sort_id = uuid.uuid4()
        cursor = encode_cursor(sort_id, record_id)
        data = decode_cursor(cursor)
        assert data["v"] == str(sort_id)

    def test_cursor_is_url_safe_string(self):
        cursor = encode_cursor("value", uuid.uuid4())
        assert " " not in cursor
        assert "+" not in cursor
        assert "/" not in cursor

    def test_decode_invalid_base64_raises_bad_request(self):
        with pytest.raises(BadRequestError):
            decode_cursor("!!!not-valid-base64!!!")

    def test_decode_valid_base64_missing_keys_raises_bad_request(self):
        import base64, json
        bad = base64.urlsafe_b64encode(json.dumps({"only": "one_key"}).encode()).decode()
        with pytest.raises(BadRequestError):
            decode_cursor(bad)

    def test_decode_empty_string_raises_bad_request(self):
        with pytest.raises(BadRequestError):
            decode_cursor("")

    def test_different_records_produce_different_cursors(self):
        id_a = uuid.uuid4()
        id_b = uuid.uuid4()
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert encode_cursor(ts, id_a) != encode_cursor(ts, id_b)


class TestPaginationParams:
    def test_defaults(self):
        p = PaginationParams()
        assert p.limit == 25
        assert p.cursor is None
        assert p.sort == "created_at"
        assert p.sort_dir == SortDir.DESC

    def test_limit_max_is_100(self):
        from pydantic import ValidationError as PydanticValidationError
        with pytest.raises(PydanticValidationError):
            PaginationParams(limit=101)

    def test_limit_min_is_1(self):
        from pydantic import ValidationError as PydanticValidationError
        with pytest.raises(PydanticValidationError):
            PaginationParams(limit=0)

    def test_sort_dir_asc(self):
        p = PaginationParams(sort_dir=SortDir.ASC)
        assert p.sort_dir == SortDir.ASC

    def test_custom_sort_field(self):
        p = PaginationParams(sort="name")
        assert p.sort == "name"


# ===========================================================================
# Part 2 — Integration tests (real DB)
# ===========================================================================

# ---------------------------------------------------------------------------
# Helper — insert N organizations with controlled created_at for ordering
# ---------------------------------------------------------------------------

async def _make_orgs(session: AsyncSession, count: int) -> list[Organization]:
    """Insert ``count`` organizations with known timestamps and return them newest-first."""
    orgs = []
    for i in range(count):
        org = Organization(
            id=uuid.uuid4(),
            name=f"Org {i:02d}",
            timezone="UTC",
            is_active=True,
            created_at=datetime(2026, 1, count - i, tzinfo=timezone.utc),
        )
        session.add(org)
        orgs.append(org)
    await session.flush()
    # Return newest-first (descending by created_at, matching default sort)
    return sorted(orgs, key=lambda o: o.created_at, reverse=True)


SORT_FIELDS = {
    "created_at": Organization.created_at,
    "name": Organization.name,
}


@pytest.mark.asyncio(loop_scope="session")
async def test_paginate_first_page_returns_items(db_session: AsyncSession):
    orgs = await _make_orgs(db_session, 5)
    stmt = select(Organization).where(Organization.name.like("Org %"))
    params = PaginationParams(limit=3)

    items, meta = await paginate(
        db_session, stmt, params=params, sort_fields=SORT_FIELDS, id_col=Organization.id
    )

    assert len(items) == 3
    assert meta.limit == 3
    assert meta.has_previous is False
    assert meta.previous_cursor is None
    # Should be the 3 newest
    assert [o.name for o in items] == [orgs[0].name, orgs[1].name, orgs[2].name]


@pytest.mark.asyncio(loop_scope="session")
async def test_paginate_has_next_when_more_exist(db_session: AsyncSession):
    await _make_orgs(db_session, 5)
    stmt = select(Organization).where(Organization.name.like("Org %"))
    params = PaginationParams(limit=3)

    _, meta = await paginate(
        db_session, stmt, params=params, sort_fields=SORT_FIELDS, id_col=Organization.id
    )

    assert meta.has_next is True
    assert meta.next_cursor is not None


@pytest.mark.asyncio(loop_scope="session")
async def test_paginate_no_next_on_last_page(db_session: AsyncSession):
    await _make_orgs(db_session, 3)
    stmt = select(Organization).where(Organization.name.like("Org %"))
    params = PaginationParams(limit=10)

    _, meta = await paginate(
        db_session, stmt, params=params, sort_fields=SORT_FIELDS, id_col=Organization.id
    )

    assert meta.has_next is False
    assert meta.next_cursor is None


@pytest.mark.asyncio(loop_scope="session")
async def test_paginate_second_page_from_cursor(db_session: AsyncSession):
    orgs = await _make_orgs(db_session, 5)
    stmt = select(Organization).where(Organization.name.like("Org %"))
    params_p1 = PaginationParams(limit=2)

    items_p1, meta_p1 = await paginate(
        db_session, stmt, params=params_p1, sort_fields=SORT_FIELDS, id_col=Organization.id
    )

    assert meta_p1.next_cursor is not None

    params_p2 = PaginationParams(limit=2, cursor=meta_p1.next_cursor)
    stmt2 = select(Organization).where(Organization.name.like("Org %"))
    items_p2, meta_p2 = await paginate(
        db_session, stmt2, params=params_p2, sort_fields=SORT_FIELDS, id_col=Organization.id
    )

    # No overlap between pages
    ids_p1 = {o.id for o in items_p1}
    ids_p2 = {o.id for o in items_p2}
    assert ids_p1.isdisjoint(ids_p2)

    # Together they cover the first 4 items
    all_ids = ids_p1 | ids_p2
    expected_ids = {o.id for o in orgs[:4]}
    assert all_ids == expected_ids

    # Page 2 knows there was a previous page
    assert meta_p2.has_previous is True
    assert meta_p2.previous_cursor is not None


@pytest.mark.asyncio(loop_scope="session")
async def test_paginate_all_pages_cover_all_items_no_duplicates(db_session: AsyncSession):
    orgs = await _make_orgs(db_session, 7)
    all_expected = {o.id for o in orgs}
    collected = set()
    cursor = None

    for _ in range(10):  # safety limit
        params = PaginationParams(limit=3, cursor=cursor)
        stmt = select(Organization).where(Organization.name.like("Org %"))
        items, meta = await paginate(
            db_session, stmt, params=params, sort_fields=SORT_FIELDS, id_col=Organization.id
        )
        for item in items:
            assert item.id not in collected, "Duplicate item across pages"
            collected.add(item.id)
        if not meta.has_next:
            break
        cursor = meta.next_cursor

    assert collected == all_expected


@pytest.mark.asyncio(loop_scope="session")
async def test_paginate_stable_after_insert(db_session: AsyncSession):
    """Items inserted after page 1 is fetched must not appear on page 2."""
    await _make_orgs(db_session, 4)
    stmt = select(Organization).where(Organization.name.like("Org %"))
    params_p1 = PaginationParams(limit=2)

    items_p1, meta_p1 = await paginate(
        db_session, stmt, params=params_p1, sort_fields=SORT_FIELDS, id_col=Organization.id
    )

    # Insert a new org with an *older* created_at (it would go on page 2+)
    late_org = Organization(
        id=uuid.uuid4(),
        name="Org Late",
        timezone="UTC",
        is_active=True,
        # Older than all existing orgs, should appear at the end
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    db_session.add(late_org)
    await db_session.flush()

    stmt2 = select(Organization).where(Organization.name.like("Org %"))
    params_p2 = PaginationParams(limit=2, cursor=meta_p1.next_cursor)
    items_p2, _ = await paginate(
        db_session, stmt2, params=params_p2, sort_fields=SORT_FIELDS, id_col=Organization.id
    )

    ids_p1 = {o.id for o in items_p1}
    ids_p2 = {o.id for o in items_p2}
    assert ids_p1.isdisjoint(ids_p2), "Page 1 items leaked into page 2 after insert"


@pytest.mark.asyncio(loop_scope="session")
async def test_paginate_invalid_sort_field_raises_400(db_session: AsyncSession):
    stmt = select(Organization)
    params = PaginationParams(sort="not_a_real_column")

    with pytest.raises(BadRequestError) as exc_info:
        await paginate(
            db_session, stmt, params=params, sort_fields=SORT_FIELDS, id_col=Organization.id
        )

    assert "not_a_real_column" in str(exc_info.value)


@pytest.mark.asyncio(loop_scope="session")
async def test_paginate_sort_ascending(db_session: AsyncSession):
    orgs = await _make_orgs(db_session, 4)
    stmt = select(Organization).where(Organization.name.like("Org %"))
    params = PaginationParams(limit=4, sort_dir=SortDir.ASC)

    items, _ = await paginate(
        db_session, stmt, params=params, sort_fields=SORT_FIELDS, id_col=Organization.id
    )

    # Ascending: oldest first
    oldest_first = sorted(orgs, key=lambda o: o.created_at)
    assert [o.id for o in items] == [o.id for o in oldest_first]


# ===========================================================================
# Part 3 — Filter helper unit tests (no DB needed)
# ===========================================================================

class TestFilterHelpers:
    """Smoke tests for filter helpers — just verify they return Select objects."""

    def _base_stmt(self):
        return select(Organization)

    def test_apply_exact_filter_with_value(self):
        stmt = apply_exact_filter(self._base_stmt(), Organization.name, "Acme")
        assert stmt is not None

    def test_apply_exact_filter_none_is_noop(self):
        base = self._base_stmt()
        result = apply_exact_filter(base, Organization.name, None)
        assert str(result) == str(base)

    def test_apply_in_filter_comma_separated(self):
        stmt = apply_in_filter(self._base_stmt(), Organization.name, "Acme,Beta,Gamma")
        assert stmt is not None

    def test_apply_in_filter_none_is_noop(self):
        base = self._base_stmt()
        result = apply_in_filter(base, Organization.name, None)
        assert str(result) == str(base)

    def test_apply_in_filter_empty_string_is_noop(self):
        base = self._base_stmt()
        result = apply_in_filter(base, Organization.name, "")
        assert str(result) == str(base)

    def test_apply_date_range_filter_both_bounds(self):
        from datetime import date
        stmt = apply_date_range_filter(
            self._base_stmt(),
            Organization.created_at,
            date(2026, 1, 1),
            date(2026, 12, 31),
        )
        assert stmt is not None

    def test_apply_date_range_filter_no_bounds_is_noop(self):
        base = self._base_stmt()
        result = apply_date_range_filter(base, Organization.created_at, None, None)
        assert str(result) == str(base)

    def test_apply_text_search_with_query(self):
        stmt = apply_text_search(self._base_stmt(), Organization.name, "clinic")
        assert stmt is not None

    def test_apply_text_search_none_is_noop(self):
        base = self._base_stmt()
        result = apply_text_search(base, Organization.name, None)
        assert str(result) == str(base)

    def test_apply_text_search_empty_string_is_noop(self):
        base = self._base_stmt()
        result = apply_text_search(base, Organization.name, "")
        assert str(result) == str(base)
