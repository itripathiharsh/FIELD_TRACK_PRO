"""Add refresh_tokens.rotated_at (reuse grace window).

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-10-11 15:00:00.000000

Refresh-token rotation reuse was treated as theft unconditionally, so two
browser tabs (or a client retry) racing on the same refresh token could
revoke every session for that user. This nullable timestamp records WHEN a
token was revoked specifically because it was rotated (as opposed to logout,
account-disable, or an actual reuse-detected revoke-all), so the refresh flow
can tell "rotated 2 seconds ago, probably a race" from "rotated 3 days ago,
this is a replayed stolen token" and only treat the latter as theft.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0f1a2b3c4d5"
down_revision: Union[str, None] = "d9e0f1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("refresh_tokens")}
    if "rotated_at" not in cols:
        op.add_column(
            "refresh_tokens",
            sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "rotated_at" in {c["name"] for c in insp.get_columns("refresh_tokens")}:
        op.drop_column("refresh_tokens", "rotated_at")
