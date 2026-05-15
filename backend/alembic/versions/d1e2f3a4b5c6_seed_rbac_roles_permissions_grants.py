"""Seed RBAC roles, permissions, and role-permission grants (SPEC-002 §3).

Creates the 11 system roles, 54 system permissions, and the full
role-permission grant matrix including row-level conditions for provider
domain roles. All seed rows have is_system_role / is_system_permission = true.

Also alters role_permissions.organization_id to nullable so system-level
grants (no org) match the same NULL-org pattern as system roles and
permissions.

Revision ID: d1e2f3a4b5c6
Revises: e730417d99c0
Create Date: 2026-05-14

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from uuid import uuid4

revision = "d1e2f3a4b5c6"
down_revision = "e730417d99c0"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Fixed UUIDs — deterministic so downstream migrations can reference them.
# ---------------------------------------------------------------------------

# Roles (prefix 00000001-)
ROLE_ADMIN            = "00000001-0000-0000-0000-000000000001"
ROLE_PRACTICE_ADMIN   = "00000001-0000-0000-0000-000000000002"
ROLE_SYSTEM_ADMIN     = "00000001-0000-0000-0000-000000000003"
ROLE_BILLER           = "00000001-0000-0000-0000-000000000004"
ROLE_RECEPTIONIST     = "00000001-0000-0000-0000-000000000005"
ROLE_PROVIDER         = "00000001-0000-0000-0000-000000000006"
ROLE_THERAPIST        = "00000001-0000-0000-0000-000000000007"
ROLE_SUPERVISOR       = "00000001-0000-0000-0000-000000000008"
ROLE_PRESCRIBER       = "00000001-0000-0000-0000-000000000009"
ROLE_CLIENT           = "00000001-0000-0000-0000-000000000010"
ROLE_GUARDIAN         = "00000001-0000-0000-0000-000000000011"

# Permissions (prefix 00000002-)
PERM_CLIENTS_READ         = "00000002-0000-0000-0000-000000000001"
PERM_CLIENTS_WRITE        = "00000002-0000-0000-0000-000000000002"
PERM_CLIENTS_DELETE       = "00000002-0000-0000-0000-000000000003"
PERM_SESSIONS_READ        = "00000002-0000-0000-0000-000000000004"
PERM_SESSIONS_WRITE       = "00000002-0000-0000-0000-000000000005"
PERM_NOTES_READ           = "00000002-0000-0000-0000-000000000006"
PERM_NOTES_WRITE          = "00000002-0000-0000-0000-000000000007"
PERM_NOTES_SIGN           = "00000002-0000-0000-0000-000000000008"
PERM_NOTES_COSIGN         = "00000002-0000-0000-0000-000000000009"
PERM_INVOICES_READ        = "00000002-0000-0000-0000-000000000010"
PERM_INVOICES_CREATE      = "00000002-0000-0000-0000-000000000011"
PERM_INVOICES_WRITE       = "00000002-0000-0000-0000-000000000012"
PERM_INVOICES_VOID        = "00000002-0000-0000-0000-000000000013"
PERM_PAYMENTS_READ        = "00000002-0000-0000-0000-000000000014"
PERM_PAYMENTS_RECORD      = "00000002-0000-0000-0000-000000000015"
PERM_INSURANCE_READ       = "00000002-0000-0000-0000-000000000016"
PERM_INSURANCE_WRITE      = "00000002-0000-0000-0000-000000000017"
PERM_CODES_READ           = "00000002-0000-0000-0000-000000000018"
PERM_CODES_WRITE          = "00000002-0000-0000-0000-000000000019"
PERM_CODES_DELETE         = "00000002-0000-0000-0000-000000000020"
PERM_SETTINGS_READ        = "00000002-0000-0000-0000-000000000021"
PERM_SETTINGS_WRITE       = "00000002-0000-0000-0000-000000000022"
PERM_PEOPLE_READ          = "00000002-0000-0000-0000-000000000023"
PERM_PEOPLE_WRITE         = "00000002-0000-0000-0000-000000000024"
PERM_PEOPLE_DELETE        = "00000002-0000-0000-0000-000000000025"
PERM_ROLES_READ           = "00000002-0000-0000-0000-000000000026"
PERM_ROLES_WRITE          = "00000002-0000-0000-0000-000000000027"
PERM_ROLES_DELETE         = "00000002-0000-0000-0000-000000000028"
PERM_ROLES_ASSIGN         = "00000002-0000-0000-0000-000000000029"
PERM_ENTITY_TYPES_READ    = "00000002-0000-0000-0000-000000000030"
PERM_ENTITY_TYPES_WRITE   = "00000002-0000-0000-0000-000000000031"
PERM_ENTITY_TYPES_DELETE  = "00000002-0000-0000-0000-000000000032"
PERM_PROVIDER_READ        = "00000002-0000-0000-0000-000000000033"
PERM_PROVIDER_WRITE       = "00000002-0000-0000-0000-000000000034"
PERM_PROVIDER_DELETE      = "00000002-0000-0000-0000-000000000035"
PERM_CLIENT_READ          = "00000002-0000-0000-0000-000000000036"
PERM_CLIENT_WRITE         = "00000002-0000-0000-0000-000000000037"
PERM_CLIENT_DELETE        = "00000002-0000-0000-0000-000000000038"
PERM_ADMIN_READ           = "00000002-0000-0000-0000-000000000039"
PERM_ADMIN_WRITE          = "00000002-0000-0000-0000-000000000040"
PERM_ADMIN_DELETE         = "00000002-0000-0000-0000-000000000041"
PERM_DOCUMENTS_READ       = "00000002-0000-0000-0000-000000000042"
PERM_DOCUMENTS_WRITE      = "00000002-0000-0000-0000-000000000043"
PERM_DOCUMENTS_DELETE     = "00000002-0000-0000-0000-000000000044"
PERM_CONSENTS_READ        = "00000002-0000-0000-0000-000000000045"
PERM_CONSENTS_WRITE       = "00000002-0000-0000-0000-000000000046"
PERM_CONSENTS_SIGN        = "00000002-0000-0000-0000-000000000047"
PERM_CONSENTS_REVOKE      = "00000002-0000-0000-0000-000000000048"
PERM_FORMS_READ           = "00000002-0000-0000-0000-000000000049"
PERM_FORMS_WRITE          = "00000002-0000-0000-0000-000000000050"
PERM_FORMS_SEND           = "00000002-0000-0000-0000-000000000051"
PERM_AUDIT_READ           = "00000002-0000-0000-0000-000000000052"
PERM_TENANTS_MANAGE       = "00000002-0000-0000-0000-000000000053"
PERM_SYSTEM_CONFIGURE     = "00000002-0000-0000-0000-000000000054"

# ---------------------------------------------------------------------------
# Row-level condition constants (SPEC-002 §6)
# ---------------------------------------------------------------------------
OWN_CLIENTS  = '{"scope": "own_clients"}'
OWN_SESSIONS = '{"scope": "own_sessions"}'
OWN_NOTES    = '{"scope": "own_notes"}'


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Make role_permissions.organization_id nullable so system-level
    #    grants can be inserted with NULL (mirrors Role / Permission).
    # ------------------------------------------------------------------
    op.alter_column(
        "role_permissions",
        "organization_id",
        existing_type=sa.UUID(),
        nullable=True,
    )

    # ------------------------------------------------------------------
    # 2. Seed permissions (54 system permissions, organization_id = NULL)
    # ------------------------------------------------------------------
    permissions = [
        # slug                   resource        action      description
        ("clients.read",         "clients",      "read",     "Read client records allowed by scope."),
        ("clients.write",        "clients",      "write",    "Create or update client records allowed by scope."),
        ("clients.delete",       "clients",      "delete",   "Soft delete client records."),
        ("sessions.read",        "sessions",     "read",     "Read session records."),
        ("sessions.write",       "sessions",     "write",    "Create, update, or cancel sessions."),
        ("notes.read",           "notes",        "read",     "Read clinical notes."),
        ("notes.write",          "notes",        "write",    "Draft and edit unsigned notes."),
        ("notes.sign",           "notes",        "sign",     "Sign notes as author."),
        ("notes.cosign",         "notes",        "cosign",   "Co-sign notes as supervisor."),
        ("invoices.read",        "invoices",     "read",     "Read invoices and line items."),
        ("invoices.create",      "invoices",     "create",   "Create new invoices for completed sessions."),
        ("invoices.write",       "invoices",     "write",    "Update invoice metadata and manage line items."),
        ("invoices.void",        "invoices",     "void",     "Void invoices with required reason."),
        ("payments.read",        "payments",     "read",     "Read payment records."),
        ("payments.record",      "payments",     "record",   "Record payments against invoices."),
        ("insurance.read",       "insurance",    "read",     "Read insurance payers and client coverage records."),
        ("insurance.write",      "insurance",    "write",    "Create and update insurance payers and coverage."),
        ("codes.read",           "codes",        "read",     "Read CPT and ICD reference code tables."),
        ("codes.write",          "codes",        "write",    "Create or update CPT and ICD codes."),
        ("codes.delete",         "codes",        "delete",   "Deactivate CPT and ICD codes."),
        ("settings.read",        "settings",     "read",     "Read organization configuration."),
        ("settings.write",       "settings",     "write",    "Update organization configuration."),
        ("people.read",          "people",       "read",     "Read person identity records."),
        ("people.write",         "people",       "write",    "Create or update person records."),
        ("people.delete",        "people",       "delete",   "Soft delete person records."),
        ("roles.read",           "roles",        "read",     "List and view roles and permissions."),
        ("roles.write",          "roles",        "write",    "Create or update custom roles and permission grants."),
        ("roles.delete",         "roles",        "delete",   "Delete custom roles."),
        ("roles.assign",         "roles",        "assign",   "Assign or revoke roles on people."),
        ("entity_types.read",    "entity_types", "read",     "List and view entity types and attributes."),
        ("entity_types.write",   "entity_types", "write",    "Create or update custom entity types."),
        ("entity_types.delete",  "entity_types", "delete",   "Delete custom entity types."),
        ("provider.read",        "provider",     "read",     "Read provider EntityInstances."),
        ("provider.write",       "provider",     "write",    "Create or update provider EntityInstances."),
        ("provider.delete",      "provider",     "delete",   "Soft delete provider EntityInstances."),
        ("client.read",          "client",       "read",     "Read client EntityInstances."),
        ("client.write",         "client",       "write",    "Create or update client EntityInstances."),
        ("client.delete",        "client",       "delete",   "Soft delete client EntityInstances."),
        ("admin.read",           "admin",        "read",     "Read admin EntityInstances."),
        ("admin.write",          "admin",        "write",    "Create or update admin EntityInstances."),
        ("admin.delete",         "admin",        "delete",   "Soft delete admin EntityInstances."),
        ("documents.read",       "documents",    "read",     "Read document metadata and download."),
        ("documents.write",      "documents",    "write",    "Upload documents and manage document types."),
        ("documents.delete",     "documents",    "delete",   "Soft delete documents."),
        ("consents.read",        "consents",     "read",     "Read client consent records and consent types."),
        ("consents.write",       "consents",     "write",    "Create and update consent records and types."),
        ("consents.sign",        "consents",     "sign",     "Record a consent as signed."),
        ("consents.revoke",      "consents",     "revoke",   "Revoke a signed consent."),
        ("forms.read",           "forms",        "read",     "Read form templates."),
        ("forms.write",          "forms",        "write",    "Create and update custom form templates."),
        ("forms.send",           "forms",        "send",     "Send forms to clients for completion."),
        ("audit.read",           "audit",        "read",     "Query the audit log."),
        ("tenants.manage",       "tenants",      "manage",   "Create, suspend, or update tenant organizations."),
        ("system.configure",     "system",       "manage",   "Platform-level operational configuration."),
    ]

    perm_ids = [
        PERM_CLIENTS_READ, PERM_CLIENTS_WRITE, PERM_CLIENTS_DELETE,
        PERM_SESSIONS_READ, PERM_SESSIONS_WRITE,
        PERM_NOTES_READ, PERM_NOTES_WRITE, PERM_NOTES_SIGN, PERM_NOTES_COSIGN,
        PERM_INVOICES_READ, PERM_INVOICES_CREATE, PERM_INVOICES_WRITE, PERM_INVOICES_VOID,
        PERM_PAYMENTS_READ, PERM_PAYMENTS_RECORD,
        PERM_INSURANCE_READ, PERM_INSURANCE_WRITE,
        PERM_CODES_READ, PERM_CODES_WRITE, PERM_CODES_DELETE,
        PERM_SETTINGS_READ, PERM_SETTINGS_WRITE,
        PERM_PEOPLE_READ, PERM_PEOPLE_WRITE, PERM_PEOPLE_DELETE,
        PERM_ROLES_READ, PERM_ROLES_WRITE, PERM_ROLES_DELETE, PERM_ROLES_ASSIGN,
        PERM_ENTITY_TYPES_READ, PERM_ENTITY_TYPES_WRITE, PERM_ENTITY_TYPES_DELETE,
        PERM_PROVIDER_READ, PERM_PROVIDER_WRITE, PERM_PROVIDER_DELETE,
        PERM_CLIENT_READ, PERM_CLIENT_WRITE, PERM_CLIENT_DELETE,
        PERM_ADMIN_READ, PERM_ADMIN_WRITE, PERM_ADMIN_DELETE,
        PERM_DOCUMENTS_READ, PERM_DOCUMENTS_WRITE, PERM_DOCUMENTS_DELETE,
        PERM_CONSENTS_READ, PERM_CONSENTS_WRITE, PERM_CONSENTS_SIGN, PERM_CONSENTS_REVOKE,
        PERM_FORMS_READ, PERM_FORMS_WRITE, PERM_FORMS_SEND,
        PERM_AUDIT_READ, PERM_TENANTS_MANAGE, PERM_SYSTEM_CONFIGURE,
    ]

    for pid, (slug, resource, action, description) in zip(perm_ids, permissions, strict=True):
        op.execute(
            sa.text(
                """
                INSERT INTO permissions
                    (id, organization_id, resource_slug, action, slug,
                     description, is_system_permission, created_at)
                VALUES
                    (CAST(:id AS uuid), NULL, :resource, :action, :slug,
                     :description, true, now())
                ON CONFLICT DO NOTHING
                """
            ).bindparams(
                id=pid, resource=resource, action=action,
                slug=slug, description=description,
            )
        )

    # ------------------------------------------------------------------
    # 3. Seed roles (11 system roles, organization_id = NULL)
    #    Inserted in dependency order so parent_role_id FK is satisfied.
    # ------------------------------------------------------------------
    # (slug, id, domain, parent_id, name, description)
    roles = [
        # Root roles — no parent
        (
            "admin", ROLE_ADMIN, "ADMIN", None,
            "Admin",
            "Primary role root for operations.",
        ),
        (
            "provider", ROLE_PROVIDER, "PROVIDER", None,
            "Provider",
            "Primary role root for clinical staff.",
        ),
        (
            "client", ROLE_CLIENT, "CLIENT", None,
            "Client",
            "Primary role root for care recipients.",
        ),
        # Standalone admin-domain roles (NOT admin children — SPEC-002 §3)
        (
            "biller", ROLE_BILLER, "ADMIN", None,
            "Biller",
            "Standalone billing role. Direct billing grants only.",
        ),
        (
            "receptionist", ROLE_RECEPTIONIST, "ADMIN", None,
            "Receptionist",
            "Standalone scheduling and intake role. Direct grants only.",
        ),
        # Admin children
        (
            "practice_admin", ROLE_PRACTICE_ADMIN, "ADMIN", ROLE_ADMIN,
            "Practice Admin",
            "Practice-level operational control. Inherits all admin grants.",
        ),
        (
            "system_admin", ROLE_SYSTEM_ADMIN, "ADMIN", ROLE_ADMIN,
            "System Admin",
            "Platform-level and tenant management. Inherits all admin grants.",
        ),
        # Provider children
        (
            "therapist", ROLE_THERAPIST, "PROVIDER", ROLE_PROVIDER,
            "Therapist",
            "Clinical care and note authoring. Inherits all provider grants.",
        ),
        (
            "supervisor", ROLE_SUPERVISOR, "PROVIDER", ROLE_PROVIDER,
            "Supervisor",
            "Therapist permissions plus co-signing.",
        ),
        (
            "prescriber", ROLE_PRESCRIBER, "PROVIDER", ROLE_PROVIDER,
            "Prescriber",
            "Therapist permissions plus prescribing (future).",
        ),
        # Client children
        (
            "guardian", ROLE_GUARDIAN, "CLIENT", ROLE_CLIENT,
            "Guardian",
            "Dependent-scoped client portal access (post-MVP).",
        ),
    ]

    for slug, rid, domain, parent_id, name, description in roles:
        op.execute(
            sa.text(
                """
                INSERT INTO roles
                    (id, organization_id, name, slug, primary_domain,
                     parent_role_id, is_system_role, description, created_at)
                VALUES
                    (CAST(:id AS uuid), NULL, :name, :slug, :domain,
                     CAST(:parent_id AS uuid), true, :description, now())
                ON CONFLICT DO NOTHING
                """
            ).bindparams(
                id=rid, name=name, slug=slug, domain=domain,
                parent_id=parent_id, description=description,
            )
        )

    # ------------------------------------------------------------------
    # 4. Seed role-permission grants (direct grants only — "inh" rows are
    #    resolved at runtime by walking parent_role_id chain).
    #    organization_id = NULL for system-level grants.
    # ------------------------------------------------------------------
    # Each tuple: (role_id, permission_id, conditions_json_or_None)
    grants: list[tuple[str, str, str | None]] = [
        # ------------------------------------------------------------------
        # admin — all "Y" grants, null conditions (unrestricted within org)
        # ------------------------------------------------------------------
        (ROLE_ADMIN, PERM_CLIENTS_READ,       None),
        (ROLE_ADMIN, PERM_CLIENTS_WRITE,      None),
        (ROLE_ADMIN, PERM_CLIENTS_DELETE,     None),
        (ROLE_ADMIN, PERM_SESSIONS_READ,      None),
        (ROLE_ADMIN, PERM_SESSIONS_WRITE,     None),
        (ROLE_ADMIN, PERM_NOTES_READ,         None),
        # notes.write intentionally omitted — admin does NOT have notes.write
        # (practice_admin gets it as a direct grant)
        (ROLE_ADMIN, PERM_INVOICES_READ,      None),
        (ROLE_ADMIN, PERM_INVOICES_CREATE,    None),
        (ROLE_ADMIN, PERM_INVOICES_WRITE,     None),
        (ROLE_ADMIN, PERM_INVOICES_VOID,      None),
        (ROLE_ADMIN, PERM_PAYMENTS_READ,      None),
        (ROLE_ADMIN, PERM_PAYMENTS_RECORD,    None),
        (ROLE_ADMIN, PERM_INSURANCE_READ,     None),
        (ROLE_ADMIN, PERM_INSURANCE_WRITE,    None),
        (ROLE_ADMIN, PERM_CODES_READ,         None),
        (ROLE_ADMIN, PERM_CODES_WRITE,        None),
        (ROLE_ADMIN, PERM_CODES_DELETE,       None),
        (ROLE_ADMIN, PERM_SETTINGS_READ,      None),
        (ROLE_ADMIN, PERM_SETTINGS_WRITE,     None),
        (ROLE_ADMIN, PERM_PEOPLE_READ,        None),
        (ROLE_ADMIN, PERM_PEOPLE_WRITE,       None),
        (ROLE_ADMIN, PERM_PEOPLE_DELETE,      None),
        (ROLE_ADMIN, PERM_ROLES_READ,         None),
        (ROLE_ADMIN, PERM_ROLES_WRITE,        None),
        (ROLE_ADMIN, PERM_ROLES_DELETE,       None),
        (ROLE_ADMIN, PERM_ROLES_ASSIGN,       None),
        (ROLE_ADMIN, PERM_ENTITY_TYPES_READ,  None),
        # entity_types.write / .delete go to system_admin only
        (ROLE_ADMIN, PERM_DOCUMENTS_READ,     None),
        (ROLE_ADMIN, PERM_DOCUMENTS_WRITE,    None),
        (ROLE_ADMIN, PERM_DOCUMENTS_DELETE,   None),
        (ROLE_ADMIN, PERM_CONSENTS_READ,      None),
        (ROLE_ADMIN, PERM_CONSENTS_WRITE,     None),
        (ROLE_ADMIN, PERM_CONSENTS_SIGN,      None),
        (ROLE_ADMIN, PERM_CONSENTS_REVOKE,    None),
        (ROLE_ADMIN, PERM_FORMS_READ,         None),
        (ROLE_ADMIN, PERM_FORMS_WRITE,        None),
        (ROLE_ADMIN, PERM_FORMS_SEND,         None),
        (ROLE_ADMIN, PERM_AUDIT_READ,         None),

        # ------------------------------------------------------------------
        # practice_admin — direct grant only (notes.write not in admin parent)
        # ------------------------------------------------------------------
        (ROLE_PRACTICE_ADMIN, PERM_NOTES_WRITE, None),

        # ------------------------------------------------------------------
        # system_admin — direct grants (entity_types + platform-level)
        # ------------------------------------------------------------------
        (ROLE_SYSTEM_ADMIN, PERM_ENTITY_TYPES_WRITE,  None),
        (ROLE_SYSTEM_ADMIN, PERM_ENTITY_TYPES_DELETE, None),
        (ROLE_SYSTEM_ADMIN, PERM_TENANTS_MANAGE,      None),
        (ROLE_SYSTEM_ADMIN, PERM_SYSTEM_CONFIGURE,    None),

        # ------------------------------------------------------------------
        # biller — standalone, direct billing grants only (SPEC-002 §3)
        # ------------------------------------------------------------------
        (ROLE_BILLER, PERM_INVOICES_READ,   None),
        (ROLE_BILLER, PERM_INVOICES_CREATE, None),
        (ROLE_BILLER, PERM_INVOICES_WRITE,  None),
        (ROLE_BILLER, PERM_INVOICES_VOID,   None),
        (ROLE_BILLER, PERM_PAYMENTS_READ,   None),
        (ROLE_BILLER, PERM_PAYMENTS_RECORD, None),
        (ROLE_BILLER, PERM_INSURANCE_READ,  None),
        (ROLE_BILLER, PERM_INSURANCE_WRITE, None),
        (ROLE_BILLER, PERM_CODES_READ,      None),
        (ROLE_BILLER, PERM_CODES_WRITE,     None),
        (ROLE_BILLER, PERM_CODES_DELETE,    None),

        # ------------------------------------------------------------------
        # receptionist — standalone, direct scheduling/intake grants
        # ------------------------------------------------------------------
        (ROLE_RECEPTIONIST, PERM_CLIENTS_READ,      None),
        (ROLE_RECEPTIONIST, PERM_CLIENTS_WRITE,     None),
        (ROLE_RECEPTIONIST, PERM_SESSIONS_READ,     None),
        (ROLE_RECEPTIONIST, PERM_SESSIONS_WRITE,    None),
        (ROLE_RECEPTIONIST, PERM_PEOPLE_READ,       None),
        (ROLE_RECEPTIONIST, PERM_CONSENTS_READ,     None),
        (ROLE_RECEPTIONIST, PERM_CONSENTS_WRITE,    None),
        (ROLE_RECEPTIONIST, PERM_CONSENTS_SIGN,     None),
        (ROLE_RECEPTIONIST, PERM_FORMS_READ,        None),
        (ROLE_RECEPTIONIST, PERM_FORMS_SEND,        None),
        (ROLE_RECEPTIONIST, PERM_ENTITY_TYPES_READ, None),

        # ------------------------------------------------------------------
        # provider — direct grants with row-level conditions (SPEC-002 §6)
        # ------------------------------------------------------------------
        (ROLE_PROVIDER, PERM_CLIENTS_READ,      OWN_CLIENTS),
        (ROLE_PROVIDER, PERM_CLIENTS_WRITE,     OWN_CLIENTS),
        (ROLE_PROVIDER, PERM_SESSIONS_READ,     OWN_SESSIONS),
        (ROLE_PROVIDER, PERM_SESSIONS_WRITE,    OWN_SESSIONS),
        (ROLE_PROVIDER, PERM_NOTES_READ,        OWN_NOTES),
        (ROLE_PROVIDER, PERM_NOTES_WRITE,       OWN_NOTES),
        (ROLE_PROVIDER, PERM_DOCUMENTS_READ,    None),
        (ROLE_PROVIDER, PERM_DOCUMENTS_WRITE,   None),
        (ROLE_PROVIDER, PERM_CONSENTS_READ,     None),
        (ROLE_PROVIDER, PERM_CONSENTS_WRITE,    None),
        (ROLE_PROVIDER, PERM_CONSENTS_SIGN,     None),
        (ROLE_PROVIDER, PERM_FORMS_READ,        None),
        (ROLE_PROVIDER, PERM_ENTITY_TYPES_READ, None),

        # ------------------------------------------------------------------
        # therapist — inherits provider grants; direct grant: notes.sign
        # ------------------------------------------------------------------
        (ROLE_THERAPIST, PERM_NOTES_SIGN, None),

        # ------------------------------------------------------------------
        # supervisor — inherits provider grants; direct grants: notes.sign,
        # notes.cosign (SPEC-002 §3: "Inherits all provider grants +
        # notes.sign + notes.cosign")
        # ------------------------------------------------------------------
        (ROLE_SUPERVISOR, PERM_NOTES_SIGN,   None),
        (ROLE_SUPERVISOR, PERM_NOTES_COSIGN, None),

        # ------------------------------------------------------------------
        # prescriber — inherits provider grants; direct grant: notes.sign
        # ------------------------------------------------------------------
        (ROLE_PRESCRIBER, PERM_NOTES_SIGN, None),

        # client and guardian — no direct grants (client portal is post-MVP)
    ]

    for role_id, perm_id, conditions in grants:
        op.execute(
            sa.text(
                """
                INSERT INTO role_permissions
                    (id, organization_id, role_id, permission_id,
                     conditions, granted_at)
                VALUES
                    (CAST(:id AS uuid), NULL,
                     CAST(:role_id AS uuid), CAST(:perm_id AS uuid),
                     CAST(:conditions AS jsonb), now())
                ON CONFLICT DO NOTHING
                """
            ).bindparams(
                id=str(uuid4()),
                role_id=role_id,
                perm_id=perm_id,
                conditions=conditions,
            )
        )


def downgrade() -> None:
    # Remove grants first (FK deps), then roles and permissions.
    role_ids = ", ".join(
        f"CAST('{r}' AS uuid)" for r in [
            ROLE_ADMIN, ROLE_PRACTICE_ADMIN, ROLE_SYSTEM_ADMIN,
            ROLE_BILLER, ROLE_RECEPTIONIST, ROLE_PROVIDER,
            ROLE_THERAPIST, ROLE_SUPERVISOR, ROLE_PRESCRIBER,
            ROLE_CLIENT, ROLE_GUARDIAN,
        ]
    )
    perm_ids_str = ", ".join(
        f"CAST('{p}' AS uuid)" for p in [
            PERM_CLIENTS_READ, PERM_CLIENTS_WRITE, PERM_CLIENTS_DELETE,
            PERM_SESSIONS_READ, PERM_SESSIONS_WRITE,
            PERM_NOTES_READ, PERM_NOTES_WRITE, PERM_NOTES_SIGN, PERM_NOTES_COSIGN,
            PERM_INVOICES_READ, PERM_INVOICES_CREATE,
            PERM_INVOICES_WRITE, PERM_INVOICES_VOID,
            PERM_PAYMENTS_READ, PERM_PAYMENTS_RECORD,
            PERM_INSURANCE_READ, PERM_INSURANCE_WRITE,
            PERM_CODES_READ, PERM_CODES_WRITE, PERM_CODES_DELETE,
            PERM_SETTINGS_READ, PERM_SETTINGS_WRITE,
            PERM_PEOPLE_READ, PERM_PEOPLE_WRITE, PERM_PEOPLE_DELETE,
            PERM_ROLES_READ, PERM_ROLES_WRITE, PERM_ROLES_DELETE, PERM_ROLES_ASSIGN,
            PERM_ENTITY_TYPES_READ, PERM_ENTITY_TYPES_WRITE, PERM_ENTITY_TYPES_DELETE,
            PERM_PROVIDER_READ, PERM_PROVIDER_WRITE, PERM_PROVIDER_DELETE,
            PERM_CLIENT_READ, PERM_CLIENT_WRITE, PERM_CLIENT_DELETE,
            PERM_ADMIN_READ, PERM_ADMIN_WRITE, PERM_ADMIN_DELETE,
            PERM_DOCUMENTS_READ, PERM_DOCUMENTS_WRITE, PERM_DOCUMENTS_DELETE,
            PERM_CONSENTS_READ, PERM_CONSENTS_WRITE,
            PERM_CONSENTS_SIGN, PERM_CONSENTS_REVOKE,
            PERM_FORMS_READ, PERM_FORMS_WRITE, PERM_FORMS_SEND,
            PERM_AUDIT_READ, PERM_TENANTS_MANAGE, PERM_SYSTEM_CONFIGURE,
        ]
    )

    op.execute(
        sa.text(f"DELETE FROM role_permissions WHERE role_id IN ({role_ids})")
    )
    # Delete leaf roles before roots (self-FK)
    leaf_role_ids = ", ".join(
        f"CAST('{r}' AS uuid)" for r in [
            ROLE_PRACTICE_ADMIN, ROLE_SYSTEM_ADMIN, ROLE_BILLER, ROLE_RECEPTIONIST,
            ROLE_THERAPIST, ROLE_SUPERVISOR, ROLE_PRESCRIBER, ROLE_GUARDIAN,
        ]
    )
    op.execute(sa.text(f"DELETE FROM roles WHERE id IN ({leaf_role_ids})"))
    root_role_ids = ", ".join(
        f"CAST('{r}' AS uuid)" for r in [ROLE_ADMIN, ROLE_PROVIDER, ROLE_CLIENT]
    )
    op.execute(sa.text(f"DELETE FROM roles WHERE id IN ({root_role_ids})"))
    op.execute(
        sa.text(f"DELETE FROM permissions WHERE id IN ({perm_ids_str})")
    )

    # Restore NOT NULL on role_permissions.organization_id
    op.alter_column(
        "role_permissions",
        "organization_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
