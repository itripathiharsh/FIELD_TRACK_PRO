"""visit duplicate protection: partial unique index on (employee_id, scheduled_at) for active visits

Revision ID: h1i2j3k4l5m6
Revises: g2h3i4j5k6l7
Create Date: 2026-08-22 11:50:00.000000

Adds a PostgreSQL partial unique index on visits(employee_id, scheduled_at)
WHERE status NOT IN ('COMPLETED', 'MISSED').

Purpose
-------
The service-layer _check_duplicate_visit() runs BEFORE the INSERT, but two
concurrent requests can each read zero conflicts and then both INSERT at the
same millisecond. The DB-level partial unique index is the last line of
defence: it makes that race result in a UniqueViolation (caught by FastAPI's
exception handler as HTTP 409) rather than a silent duplicate row.

Why a *partial* index?
- Completed and missed visits are terminal. Rescheduling the same employee
  to the same slot after a past visit has finished must be allowed.
- A full unique index on (employee_id, scheduled_at) would block that.
- PostgreSQL partial indexes support WHERE clauses, giving us the precise
  semantic: "unique per active visits only".

The index also serves as a performance optimisation for the exact-duplicate
case (same employee_id + same scheduled_at), resolving it in O(log n) without
a range scan.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "h1i2j3k4l5m6"
down_revision: Union[str, Sequence[str], None] = "g2h3i4j5k6l7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Partial unique index: uniqueness is only enforced for non-terminal visits.
    # The WHERE clause mirrors the _ACTIVE_STATUSES tuple in VisitRepository.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS
            uq_visits_employee_scheduled_active
        ON visits (employee_id, scheduled_at)
        WHERE status NOT IN ('COMPLETED', 'MISSED')
    """)

    # Covering index for the range-overlap query in find_conflicting_visit():
    #   WHERE employee_id = ? AND status IN (...) AND scheduled_at BETWEEN ? AND ?
    # employee_id + scheduled_at already covered by the partial index above for
    # the active-status subset; this composite index is a fallback for queries
    # that do not hit the partial index (e.g. admin list queries).
    # Only create if it doesn't already exist (idempotent).
    op.execute("""
        CREATE INDEX IF NOT EXISTS
            ix_visits_employee_scheduled_at
        ON visits (employee_id, scheduled_at)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_visits_employee_scheduled_at")
    op.execute("DROP INDEX IF EXISTS uq_visits_employee_scheduled_active")
