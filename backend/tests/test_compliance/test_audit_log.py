"""
Tests for AuditLog model and audit service (SPEC-006 §2, §4, §7).

Test cases from SPEC-006 §9 test table:
  test_state_change_writes_audit_entry
  test_audit_failure_rolls_back_business_operation
  test_audit_snapshot_excludes_phi_fields
  test_update_audit_log_row_rejected
  test_delete_audit_log_row_rejected
  test_system_triggered_audit_has_null_actor
  test_audit_log_filters_by_org

The immutability tests require the trigger from migration
b2e4f6a8c0d1_audit_log_immutability_trigger.py to be installed.
A module-scoped fixture installs it against the test DB if not already present.
"""

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.security import AuthContext, get_auth_context
from app.main import create_app
from app.models.compliance import AuditLog
from app.models.eav import Organization
from app.services import audit_service
from app.services.audit_service import PHI_EXCLUDED_FIELDS, filter_phi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


async def _make_org(session: AsyncSession, name: str = "Test Org") -> Organization:
    org = Organization(
        id=uuid.uuid4(),
        name=name,
        timezone="UTC",
        is_active=True,
        created_at=_utc(2026, 1, 1),
    )
    session.add(org)
    await session.flush()
    return org


# ---------------------------------------------------------------------------
# Module fixture: install immutability trigger on test DB
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module", loop_scope="session", autouse=True)
async def install_immutability_trigger(test_engine: AsyncEngine):
    """Ensure the audit_log immutability triggers exist in the test DB.

    Mirrors the production Alembic migration b2e4f6a8c0d1 so the immutability
    tests run correctly without requiring the full migration pipeline.
    """
    # asyncpg cannot execute multiple SQL commands in a single prepared
    # statement, so each DDL command must be issued separately.
    async with test_engine.begin() as conn:
        await conn.execute(
            text("""
            CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
            RETURNS TRIGGER LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION
                    'AuditLog rows are immutable: % on audit_logs is not permitted.',
                    TG_OP;
            END;
            $$;
        """)
        )
        await conn.execute(text("DROP TRIGGER IF EXISTS audit_log_immutable_update ON audit_logs"))
        await conn.execute(
            text("""
            CREATE TRIGGER audit_log_immutable_update
            BEFORE UPDATE ON audit_logs
            FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation()
        """)
        )
        await conn.execute(text("DROP TRIGGER IF EXISTS audit_log_immutable_delete ON audit_logs"))
        await conn.execute(
            text("""
            CREATE TRIGGER audit_log_immutable_delete
            BEFORE DELETE ON audit_logs
            FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation()
        """)
        )


# ---------------------------------------------------------------------------
# Auth stub fixture for endpoint tests
# ---------------------------------------------------------------------------


@pytest.fixture
def audit_client(db_session: AsyncSession):
    """HTTP client with audit.read permission stubbed in."""
    app = create_app()

    stub_auth = AuthContext(
        person_id=uuid.uuid4(),
        auth_subject="test|subject",
        organization_id=uuid.uuid4(),
        permissions={"audit.read"},
    )
    app.dependency_overrides[get_auth_context] = lambda: stub_auth

    async def _override_db():
        yield db_session

    from app.core.dependencies import get_db

    app.dependency_overrides[get_db] = _override_db

    return app


# ===========================================================================
# SPEC-006 §9 named test cases
# ===========================================================================


@pytest.mark.asyncio
async def test_state_change_writes_audit_entry(db_session: AsyncSession):
    """BR-07: log_action() adds an AuditLog row to the current transaction."""
    org = await _make_org(db_session)
    resource_id = uuid.uuid4()

    entry = await audit_service.log_action(
        db_session,
        org_id=org.id,
        actor_id=None,
        action="create",
        resource_type="Organization",
        resource_id=resource_id,
        next_state={"name": "New Org"},
    )
    await db_session.flush()

    result = await db_session.get(AuditLog, entry.id)
    assert result is not None
    assert result.action == "create"
    assert result.resource_type == "Organization"
    assert result.resource_id == resource_id
    assert result.organization_id == org.id


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_business_operation(db_session: AsyncSession):
    """BR-07: when the audit write and domain write are in the same transaction,
    rolling back removes both (atomicity guarantee per SPEC-006 §7)."""
    org = await _make_org(db_session, "Atomicity Org")

    # Simulate a service: domain write + audit write in same session
    target_id = uuid.uuid4()
    new_org = Organization(
        id=target_id,
        name="Should Disappear",
        timezone="UTC",
        is_active=True,
        created_at=_utc(2026, 1, 2),
    )
    db_session.add(new_org)

    audit_entry = await audit_service.log_action(
        db_session,
        org_id=org.id,
        actor_id=None,
        action="create",
        resource_type="Organization",
        resource_id=target_id,
        next_state={"name": "Should Disappear"},
    )
    await db_session.flush()

    # Both are visible inside the transaction
    assert await db_session.get(Organization, target_id) is not None
    assert await db_session.get(AuditLog, audit_entry.id) is not None

    # Rollback (simulating an exception in the service layer)
    await db_session.rollback()

    # Both writes are gone — atomicity confirmed
    assert await db_session.get(Organization, target_id) is None
    assert await db_session.get(AuditLog, audit_entry.id) is None


@pytest.mark.asyncio
async def test_audit_snapshot_excludes_phi_fields(db_session: AsyncSession):
    """BR-08: filter_phi() strips all PHI_EXCLUDED_FIELDS from snapshots."""
    phi_snapshot = {
        "id": str(uuid.uuid4()),
        "name": "Jane Doe",
        "date_of_birth": "1990-01-01",  # PHI
        "dob": "1990-01-01",  # PHI alias
        "content": {"subjective": "..."},  # PHI
        "value": "some attribute value",  # PHI
        "notes": "sensitive clinical note",  # PHI
        "ssn": "123-45-6789",  # PHI
        # BR-08 clinical-note format keys at top level (not just under `content`):
        "subjective": "patient reports ...",
        "objective": "vitals normal ...",
        "assessment": "dx notes ...",
        "plan": "follow up in 2w ...",
        "data": "session data ...",
        "intervention": "CBT exercise ...",
        "response": "client engaged ...",
        "behavior": "cooperative ...",
        "status": "active",  # safe
    }
    org = await _make_org(db_session)
    resource_id = uuid.uuid4()

    entry = await audit_service.log_action(
        db_session,
        org_id=org.id,
        actor_id=None,
        action="update",
        resource_type="Person",
        resource_id=resource_id,
        previous_state=phi_snapshot,
        next_state={"status": "inactive", "value": "should be stripped"},
    )
    await db_session.flush()

    result = await db_session.get(AuditLog, entry.id)
    assert result is not None

    # previous_state must not contain any PHI fields
    prev = result.previous_state or {}
    for phi_field in PHI_EXCLUDED_FIELDS:
        assert phi_field not in prev, f"PHI field '{phi_field}' leaked into previous_state"

    # Non-PHI fields are preserved
    assert prev.get("status") == "active"
    assert prev.get("name") == "Jane Doe"

    # next_state PHI also stripped
    nxt = result.next_state or {}
    assert "value" not in nxt
    assert nxt.get("status") == "inactive"


@pytest.mark.asyncio
async def test_update_audit_log_row_rejected(db_session: AsyncSession):
    """AuditLog rows cannot be modified (DB-level trigger, SPEC-006 §2)."""
    org = await _make_org(db_session)
    entry = await audit_service.log_action(
        db_session,
        org_id=org.id,
        actor_id=None,
        action="create",
        resource_type="Organization",
        resource_id=org.id,
    )
    await db_session.flush()

    with pytest.raises(DBAPIError, match="immutable"):
        await db_session.execute(
            update(AuditLog).where(AuditLog.id == entry.id).values(action="tampered")
        )
        await db_session.flush()


@pytest.mark.asyncio
async def test_delete_audit_log_row_rejected(db_session: AsyncSession):
    """AuditLog rows cannot be deleted (DB-level trigger, SPEC-006 §2)."""
    from sqlalchemy import delete as sa_delete

    org = await _make_org(db_session)
    entry = await audit_service.log_action(
        db_session,
        org_id=org.id,
        actor_id=None,
        action="create",
        resource_type="Organization",
        resource_id=org.id,
    )
    await db_session.flush()

    with pytest.raises(DBAPIError, match="immutable"):
        await db_session.execute(sa_delete(AuditLog).where(AuditLog.id == entry.id))
        await db_session.flush()


@pytest.mark.asyncio
async def test_system_triggered_audit_has_null_actor(db_session: AsyncSession):
    """Cron/system-initiated events set actor_person_id to NULL (SPEC-006 §7)."""
    org = await _make_org(db_session)
    resource_id = uuid.uuid4()

    entry = await audit_service.log_action(
        db_session,
        org_id=org.id,
        actor_id=None,  # system event
        action="expire",
        resource_type="ClientConsent",
        resource_id=resource_id,
    )
    await db_session.flush()

    result = await db_session.get(AuditLog, entry.id)
    assert result is not None
    assert result.actor_person_id is None


@pytest.mark.asyncio
async def test_audit_log_filters_by_org(db_session: AsyncSession):
    """Audit entries for org A must not appear when filtering by org B."""
    org_a = await _make_org(db_session, "Org A")
    org_b = await _make_org(db_session, "Org B")

    resource_a = uuid.uuid4()
    resource_b = uuid.uuid4()

    await audit_service.log_action(
        db_session,
        org_id=org_a.id,
        actor_id=None,
        action="create",
        resource_type="Widget",
        resource_id=resource_a,
    )
    await audit_service.log_action(
        db_session,
        org_id=org_b.id,
        actor_id=None,
        action="create",
        resource_type="Widget",
        resource_id=resource_b,
    )
    await db_session.flush()

    rows_a = (
        (await db_session.execute(select(AuditLog).where(AuditLog.organization_id == org_a.id)))
        .scalars()
        .all()
    )
    rows_b = (
        (await db_session.execute(select(AuditLog).where(AuditLog.organization_id == org_b.id)))
        .scalars()
        .all()
    )

    assert all(r.organization_id == org_a.id for r in rows_a)
    assert all(r.organization_id == org_b.id for r in rows_b)
    assert {r.resource_id for r in rows_a}.isdisjoint({r.resource_id for r in rows_b})


# ===========================================================================
# filter_phi() unit tests
# ===========================================================================


class TestFilterPhi:
    def test_none_input_returns_none(self):
        assert filter_phi(None) is None

    def test_empty_dict_returns_empty(self):
        assert filter_phi({}) == {}

    def test_strips_all_phi_fields(self):
        snapshot = {field: "value" for field in PHI_EXCLUDED_FIELDS}
        snapshot["safe_field"] = "keep me"
        result = filter_phi(snapshot)
        assert result == {"safe_field": "keep me"}

    def test_does_not_mutate_input(self):
        original = {"date_of_birth": "1990-01-01", "name": "Alice"}
        _ = filter_phi(original)
        assert "date_of_birth" in original

    def test_safe_fields_pass_through(self):
        snapshot = {"id": "abc", "status": "active", "organization_id": "xyz"}
        assert filter_phi(snapshot) == snapshot

    def test_filter_phi_strips_nested_dict_keys(self):
        """PHI hidden inside nested dicts must also be stripped (recursion)."""
        snapshot = {"outer": {"subjective": "PHI content", "keep": "ok"}}
        assert filter_phi(snapshot) == {"outer": {"keep": "ok"}}

    def test_filter_phi_strips_list_of_dicts(self):
        """Lists of dicts (e.g. invoice line items) must be recursed element-wise."""
        snapshot = {
            "items": [
                {"dob": "1990-01-01", "id": 1},
                {"dob": "1991-02-02", "id": 2},
            ]
        }
        result = filter_phi(snapshot)
        assert result == {"items": [{"id": 1}, {"id": 2}]}

    def test_filter_phi_strips_top_level_clinical_note_keys(self):
        """BR-08: all 8 clinical-note format keys are PHI at any level."""
        clinical_note_keys = [
            "subjective",
            "objective",
            "assessment",
            "plan",
            "data",
            "intervention",
            "response",
            "behavior",
        ]
        snapshot = {key: f"note text for {key}" for key in clinical_note_keys}
        snapshot["id"] = "abc123"
        result = filter_phi(snapshot)
        for key in clinical_note_keys:
            assert key not in result, f"clinical-note key '{key}' leaked"
        assert result == {"id": "abc123"}

    def test_filter_phi_strips_dob_alias(self):
        """`dob` is an alias for date_of_birth and must be stripped."""
        assert filter_phi({"dob": "1990-01-01"}) == {}

    def test_filter_phi_preserves_non_phi_structure(self):
        """Deeply nested non-PHI data must round-trip unchanged."""
        snapshot = {
            "a": {"b": {"c": "deep", "list": [{"x": 1}, {"y": 2}]}},
            "top": "safe",
        }
        # Use copy to confirm non-mutation of nested structures too.
        import copy

        original = copy.deepcopy(snapshot)
        assert filter_phi(snapshot) == original
        assert snapshot == original

    def test_filter_phi_none_and_empty_inputs(self):
        """None stays None; {} stays {}; [] stays []."""
        assert filter_phi(None) is None
        assert filter_phi({}) == {}
        assert filter_phi([]) == []

    def test_filter_phi_top_level_list_input(self):
        """Top-level list input is supported (dict | list | None signature)."""
        assert filter_phi([{"dob": "1990", "id": 1}, {"id": 2}]) == [
            {"id": 1},
            {"id": 2},
        ]


class TestPhiExclusionListCentralization:
    """SPEC-006 §7: single centralized PHI exclusion list across the platform."""

    def test_audit_service_and_logger_share_the_same_constant(self):
        """audit_service.PHI_EXCLUDED_FIELDS must be the same object as logger's."""
        from app.core import logger as logger_module
        from app.core.phi import PHI_EXCLUDED_FIELDS as canonical
        from app.services import audit_service as audit_module

        assert audit_module.PHI_EXCLUDED_FIELDS is canonical
        # The logger's processor must consult the canonical set.
        assert getattr(logger_module, "PHI_EXCLUDED_FIELDS", None) is canonical

    def test_canonical_set_covers_br08_and_logger_additions(self):
        """Union of previous audit + logger fields + BR-08 additions is covered."""
        from app.core.phi import PHI_EXCLUDED_FIELDS

        required = {
            # original audit_service list
            "content",
            "date_of_birth",
            "ssn",
            "emergency_contact_name",
            "emergency_contact_phone",
            "value",
            "notes",
            "description",
            "diagnosis_codes",
            # original logger list aliases
            "note_content",
            "dob",
            "icd_codes",
            "social_security",
            # BR-08 clinical-note format keys
            "subjective",
            "objective",
            "assessment",
            "plan",
            "data",
            "intervention",
            "response",
            "behavior",
        }
        missing = required - PHI_EXCLUDED_FIELDS
        assert not missing, f"canonical PHI list is missing: {missing}"

    def test_logger_phi_filter_strips_canonical_fields(self):
        """The structlog processor must drop any key in the canonical set."""
        from app.core.logger import phi_filter
        from app.core.phi import PHI_EXCLUDED_FIELDS

        event = {field: "leak" for field in PHI_EXCLUDED_FIELDS}
        event["event"] = "something happened"
        out = phi_filter(None, "info", event)  # type: ignore[arg-type]
        assert out == {"event": "something happened"}
