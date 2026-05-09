"""
Shared fixtures for the test_eav package.

``seed_eav_data`` replicates what the Alembic migration c3f5e7a9b1d2 does,
because the test suite uses ``create_all`` (DDL only) rather than running
migrations.  ORM inserts are used instead of raw SQL to avoid asyncpg's
conflict between ``:param`` named parameters and ``::jsonb`` cast syntax.

``test_org`` inserts a real Organization row with the UUID that the stub
AuthContext uses as organization_id, so EntityType FK constraints don't
fire during custom-type creation tests.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest_asyncio

from app.core.database import Database
from app.models.models import EntityAttribute, EntityType, FieldType, Organization

# Must match TASK-010 migration revision c3f5e7a9b1d2.
PROVIDER_ID = UUID("00000000-0000-0000-0000-000000000001")
CLIENT_ID = UUID("00000000-0000-0000-0000-000000000002")
ADMIN_ID = UUID("00000000-0000-0000-0000-000000000003")

# Must match _ORG_ID in test_entity_types.py.
TEST_ORG_ID = UUID("00000000-0000-0000-0000-0000000000c1")

# Must match organization_id in test_organizations.py stub_auth.
ORGS_TEST_ORG_ID = UUID("00000000-0000-0000-0000-0000000000b2")


def _now() -> datetime:
    return datetime.now(tz=UTC)


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def seed_eav_data(create_tables) -> None:  # depends on create_tables for fixture ordering
    """Insert seed system EntityTypes + attributes and test org rows once per session."""
    factory = Database.get_session_factory()
    async with factory() as session:
        # ----------------------------------------------------------------
        # Test organizations (FK anchors for entity-type and org tests)
        # ----------------------------------------------------------------
        for org_id, org_name in [
            (TEST_ORG_ID, "Entity-Type Tests Org"),
            (ORGS_TEST_ORG_ID, "Org Tests Org"),
        ]:
            existing_org = await session.get(Organization, org_id)
            if existing_org is None:
                session.add(
                    Organization(
                        id=org_id,
                        name=org_name,
                        timezone="UTC",
                        is_active=True,
                        created_at=_now(),
                        updated_at=_now(),
                    )
                )

        # ----------------------------------------------------------------
        # System EntityTypes
        # ----------------------------------------------------------------
        system_types = [
            (PROVIDER_ID, "provider", "provider"),
            (CLIENT_ID, "client", "client"),
            (ADMIN_ID, "admin", "admin"),
        ]
        for et_id, name, slug in system_types:
            existing_type = await session.get(EntityType, et_id)
            if existing_type is None:
                session.add(
                    EntityType(
                        id=et_id,
                        organization_id=None,
                        name=name,
                        slug=slug,
                        is_system_type=True,
                        is_person_subtype=True,
                        created_at=_now(),
                        updated_at=_now(),
                    )
                )

        await session.flush()

        # ----------------------------------------------------------------
        # Provider attributes
        # ----------------------------------------------------------------
        provider_attrs: list[tuple[str, str, FieldType, bool, object, int]] = [
            ("license_number", "License Number", FieldType.TEXT, True, None, 0),
            ("license_state", "License State", FieldType.TEXT, True, None, 1),
            ("npi_number", "NPI Number", FieldType.TEXT, False, None, 2),
            ("specialty", "Specialty", FieldType.TEXT, False, None, 3),
            ("taxonomy_code", "Taxonomy Code", FieldType.TEXT, False, None, 4),
            ("dea_number", "DEA Number", FieldType.TEXT, False, None, 5),
        ]
        for name, display_name, ft, is_req, opts, order in provider_attrs:
            session.add(
                EntityAttribute(
                    id=uuid4(),
                    entity_type_id=PROVIDER_ID,
                    name=name,
                    display_name=display_name,
                    field_type=ft,
                    is_required=is_req,
                    options=opts,
                    display_order=order,
                    created_at=_now(),
                    updated_at=_now(),
                )
            )

        # ----------------------------------------------------------------
        # Client attributes
        # ----------------------------------------------------------------
        client_attrs: list[tuple[str, str, FieldType, bool, object, int]] = [
            (
                "intake_status",
                "Intake Status",
                FieldType.ENUM,
                True,
                ["new", "in_progress", "complete"],
                0,
            ),
            ("referral_source", "Referral Source", FieldType.TEXT, False, None, 1),
            ("emergency_contact_name", "Emergency Contact Name", FieldType.TEXT, False, None, 2),
            ("emergency_contact_phone", "Emergency Contact Phone", FieldType.TEXT, False, None, 3),
            ("onboarded_at", "Onboarded At", FieldType.DATE, False, None, 4),
        ]
        for name, display_name, ft, is_req, opts, order in client_attrs:
            session.add(
                EntityAttribute(
                    id=uuid4(),
                    entity_type_id=CLIENT_ID,
                    name=name,
                    display_name=display_name,
                    field_type=ft,
                    is_required=is_req,
                    options=opts,
                    display_order=order,
                    created_at=_now(),
                    updated_at=_now(),
                )
            )

        # ----------------------------------------------------------------
        # Admin attributes
        # ----------------------------------------------------------------
        admin_attrs: list[tuple[str, str, FieldType, bool, object, int]] = [
            ("department", "Department", FieldType.TEXT, False, None, 0),
            ("title", "Title", FieldType.TEXT, False, None, 1),
        ]
        for name, display_name, ft, is_req, opts, order in admin_attrs:
            session.add(
                EntityAttribute(
                    id=uuid4(),
                    entity_type_id=ADMIN_ID,
                    name=name,
                    display_name=display_name,
                    field_type=ft,
                    is_required=is_req,
                    options=opts,
                    display_order=order,
                    created_at=_now(),
                    updated_at=_now(),
                )
            )

        await session.commit()
