"""audit_log_immutability_trigger

Installs PostgreSQL triggers that reject any UPDATE or DELETE on the
audit_logs table.  AuditLog rows are immutable by design (SPEC-006 §2).

Revision ID: b2e4f6a8c0d1
Revises: a68701f39fed
Create Date: 2026-03-26
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "b2e4f6a8c0d1"
down_revision = "a68701f39fed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Trigger function — shared by both triggers
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION
                'AuditLog rows are immutable: % on audit_logs is not permitted.',
                TG_OP;
        END;
        $$;
    """)

    # Reject UPDATE
    op.execute("""
        CREATE TRIGGER audit_log_immutable_update
        BEFORE UPDATE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();
    """)

    # Reject DELETE
    op.execute("""
        CREATE TRIGGER audit_log_immutable_delete
        BEFORE DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_immutable_update ON audit_logs;")
    op.execute("DROP TRIGGER IF EXISTS audit_log_immutable_delete ON audit_logs;")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_log_mutation();")
