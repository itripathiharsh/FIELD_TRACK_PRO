"""SUPER_ADMIN role, session token versioning, temporary-password expiry and security audit log.

Revision ID: b9c0d1e2f3a4
Revises: a7b8c9d0e1f2
Create Date: 2026-10-18 12:00:00.000000

* role_enum gains SUPER_ADMIN. Nothing is promoted by this migration: existing ADMIN accounts stay
  ADMIN. The first Super Admin is established deliberately with scripts/bootstrap_super_admin.py.
* users.token_version (int, default 0): bumped to invalidate every outstanding access token of an
  account at once (admin password reset, role change, deactivation). Existing sessions keep working
  (their tokens count as version 0).
* users.temp_password_expires_at (nullable): set only while an admin-issued temporary password is
  pending; NULL for every existing account, so no existing credential gains an expiry.
* security_audit_logs: append-only trail of privileged actions (never holds credentials).

Idempotent / inspector-guarded. Downgrade drops the new columns and table; PostgreSQL cannot drop a
single enum value, so SUPER_ADMIN stays in role_enum (harmless) - but any SUPER_ADMIN rows are first
demoted to ADMIN so the older code never sees a role it cannot represent.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b9c0d1e2f3a4"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE must commit before the new value can be used; the autocommit block
    # also makes this safe on PostgreSQL versions that forbid it inside a transaction.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE role_enum ADD VALUE IF NOT EXISTS 'SUPER_ADMIN'")

    bind = op.get_bind()
    insp = sa.inspect(bind)

    user_cols = {c["name"] for c in insp.get_columns("users")}
    if "token_version" not in user_cols:
        op.add_column("users", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))
    if "temp_password_expires_at" not in user_cols:
        op.add_column("users", sa.Column("temp_password_expires_at", sa.DateTime(timezone=True), nullable=True))

    if "security_audit_logs" not in set(insp.get_table_names()):
        uuid_t = postgresql.UUID(as_uuid=True)
        op.create_table(
            "security_audit_logs",
            sa.Column("id", uuid_t, primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("outcome", sa.String(length=16), nullable=False),
            sa.Column("actor_user_id", uuid_t, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("target_user_id", uuid_t, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("previous_role", sa.String(length=20), nullable=True),
            sa.Column("new_role", sa.String(length=20), nullable=True),
            sa.Column("reason_code", sa.String(length=64), nullable=True),
            sa.Column("details", sa.JSON(), nullable=True),
            sa.Column("request_id", sa.String(length=64), nullable=True),
            sa.Column("client_ip", sa.String(length=64), nullable=True),
        )
        op.create_index("ix_security_audit_logs_created_at", "security_audit_logs", ["created_at"])
        op.create_index("ix_security_audit_logs_event_type", "security_audit_logs", ["event_type"])
        op.create_index("ix_security_audit_logs_outcome", "security_audit_logs", ["outcome"])
        op.create_index("ix_security_audit_logs_actor_user_id", "security_audit_logs", ["actor_user_id"])
        op.create_index("ix_security_audit_logs_target_user_id", "security_audit_logs", ["target_user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "security_audit_logs" in set(insp.get_table_names()):
        op.drop_table("security_audit_logs")

    # Older code cannot represent SUPER_ADMIN: demote before leaving (the enum label itself stays).
    op.execute("UPDATE users SET role = 'ADMIN' WHERE role::text = 'SUPER_ADMIN'")

    user_cols = {c["name"] for c in sa.inspect(bind).get_columns("users")}
    if "temp_password_expires_at" in user_cols:
        op.drop_column("users", "temp_password_expires_at")
    if "token_version" in user_cols:
        op.drop_column("users", "token_version")
