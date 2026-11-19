"""ACCOUNTANT role: web-only, read-only access to the financial reports and collections.

Revision ID: j3d4e5f6a7b8
Revises: i2c3d4e5f6a7
Create Date: 2026-11-19 18:00:00.000000

* role_enum gains the label 'ACCOUNTANT'. Additive: no existing row changes, no table is rewritten.

Downgrade: older code cannot represent ACCOUNTANT, so any such account is disabled (is_active = false,
sessions revoked) and parked as EMPLOYEE before leaving. PostgreSQL cannot drop an enum label, so the
label itself stays (harmless).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "j3d4e5f6a7b8"
down_revision: Union[str, None] = "i2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE must commit before the new value can be used.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE role_enum ADD VALUE IF NOT EXISTS 'ACCOUNTANT'")


def downgrade() -> None:
    op.execute(
        "UPDATE users SET is_active = false, token_version = token_version + 1, role = 'EMPLOYEE' "
        "WHERE role::text = 'ACCOUNTANT'"
    )
