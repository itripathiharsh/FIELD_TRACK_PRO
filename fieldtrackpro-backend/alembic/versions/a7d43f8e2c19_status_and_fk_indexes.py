"""add missing indexes: visits.status, payments.status, visits FK columns (P2-5)

Revision ID: a7d43f8e2c19
Revises: e2b7f4a91c63
Create Date: 2026-08-13 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "a7d43f8e2c19"
down_revision: Union[str, Sequence[str], None] = "e2b7f4a91c63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # payments.customer_id/employee_id/invoice_id/visit_id already have
    # indexes (see d4f8a92c1e67); only status was missing, despite being
    # the primary filter for the accountant review queue
    # (PaymentRepository.list_queue) and the VERIFIED-amount aggregate in
    # employee_activity_service.
    op.create_index(op.f("ix_payments_status"), "payments", ["status"])

    # visits.customer_id/employee_id are foreign keys that Postgres does not
    # auto-index, and are filtered/joined on in VisitRepository.list_filtered,
    # get_overdue_pending, account_service/customer_service's visited-outlet
    # check, and report_service's per-employee aggregate. visits.status backs
    # the same list/report/scheduler queries.
    op.create_index(op.f("ix_visits_customer_id"), "visits", ["customer_id"])
    op.create_index(op.f("ix_visits_employee_id"), "visits", ["employee_id"])
    op.create_index(op.f("ix_visits_status"), "visits", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_visits_status"), table_name="visits")
    op.drop_index(op.f("ix_visits_employee_id"), table_name="visits")
    op.drop_index(op.f("ix_visits_customer_id"), table_name="visits")
    op.drop_index(op.f("ix_payments_status"), table_name="payments")
