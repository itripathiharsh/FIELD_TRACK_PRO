"""Add notifications.payment_id (alert -> payment reference).

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-10-10 16:00:00.000000

Failed / stuck Tally-post alerts used to carry the payment reference only in
the message text. This nullable FK (ON DELETE SET NULL, indexed) lets clients
deep-link to the payment and lets the stuck-post alert dedupe without parsing
text. Guards are idempotent (inspector-checked).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d9e0f1a2b3c4"
down_revision: Union[str, None] = "c8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_IDX = "ix_notifications_payment_id"
_FK = "fk_notifications_payment_id_payments"


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("notifications")}
    if "payment_id" not in cols:
        op.add_column("notifications", sa.Column("payment_id", sa.UUID(), nullable=True))
    insp = sa.inspect(op.get_bind())
    has_fk = any(
        fk.get("referred_table") == "payments" and fk.get("constrained_columns") == ["payment_id"]
        for fk in insp.get_foreign_keys("notifications")
    )
    if not has_fk:
        op.create_foreign_key(_FK, "notifications", "payments", ["payment_id"], ["id"], ondelete="SET NULL")
    if _IDX not in {i["name"] for i in insp.get_indexes("notifications")}:
        op.create_index(_IDX, "notifications", ["payment_id"])


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if _IDX in {i["name"] for i in insp.get_indexes("notifications")}:
        op.drop_index(_IDX, table_name="notifications")
    for fk in insp.get_foreign_keys("notifications"):
        if fk.get("constrained_columns") == ["payment_id"] and fk.get("name"):
            op.drop_constraint(fk["name"], "notifications", type_="foreignkey")
    if "payment_id" in {c["name"] for c in insp.get_columns("notifications")}:
        op.drop_column("notifications", "payment_id")
