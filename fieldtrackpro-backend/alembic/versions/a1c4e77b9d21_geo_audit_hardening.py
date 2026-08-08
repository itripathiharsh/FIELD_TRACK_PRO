"""geo audit hardening: verification_type, idempotency uniqueness, immutability

Repairs FT-031, FT-033 and FT-032.

FT-031  geo_verification_logs could not distinguish a check-in attempt from a
        check-out attempt, so the audit trail could not answer the first
        question an administrator asks about a flagged visit.

FT-033  idempotency_key had no uniqueness guarantee, so a retried check-in
        could write duplicate audit rows (fraud audit VULN-09).

FT-032  Security Design section 4 requires geo_verification_logs to be
        insert-only at the DATABASE level, not merely by application
        convention. UPDATE and DELETE are revoked from the application role.
        DELETE remains available via the ON DELETE CASCADE from visits, which
        is a table-level constraint action rather than a statement by the
        application role.

Revision ID: a1c4e77b9d21
Revises: 02bc15442e20
Create Date: 2026-08-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1c4e77b9d21"
down_revision: Union[str, Sequence[str], None] = "02bc15442e20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The least-privilege application role. Grants are only adjusted when the role
# exists, so the migration remains runnable on a developer machine that still
# connects as a superuser.
APP_ROLE = "fieldtrack_app"


def upgrade() -> None:
    # --- FT-031: verification_type -----------------------------------------
    geo_type = sa.Enum("CHECK_IN", "CHECK_OUT", name="geo_verification_type_enum")
    geo_type.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "geo_verification_logs",
        sa.Column(
            "verification_type",
            geo_type,
            nullable=False,
            server_default="CHECK_IN",
        ),
    )

    # Backfill: a row whose visit already has a check-out timestamp and which is
    # the latest attempt for that visit is most likely the check-out event.
    # Anything ambiguous stays CHECK_IN, which is the conservative reading.
    op.execute(
        """
        UPDATE geo_verification_logs g
        SET verification_type = 'CHECK_OUT'
        FROM visits v
        WHERE g.visit_id = v.id
          AND v.check_out_at IS NOT NULL
          AND g.is_valid = true
          AND g.attempted_at = (
              SELECT max(g2.attempted_at)
              FROM geo_verification_logs g2
              WHERE g2.visit_id = g.visit_id AND g2.is_valid = true
          )
          AND EXISTS (
              SELECT 1 FROM geo_verification_logs g3
              WHERE g3.visit_id = g.visit_id AND g3.is_valid = true
                AND g3.attempted_at < g.attempted_at
          )
        """
    )

    # --- FT-033: idempotency uniqueness ------------------------------------
    # Partial unique index: multiple NULL keys are allowed (most attempts carry
    # no key), but a given key may appear only once per visit.
    op.create_index(
        "uq_geo_log_visit_idempotency",
        "geo_verification_logs",
        ["visit_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    # --- FT-032: audit immutability ----------------------------------------
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                REVOKE UPDATE, DELETE, TRUNCATE
                    ON TABLE geo_verification_logs FROM {APP_ROLE};
                GRANT SELECT, INSERT ON TABLE geo_verification_logs TO {APP_ROLE};
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE
                    ON TABLE geo_verification_logs TO {APP_ROLE};
            END IF;
        END
        $$;
        """
    )

    op.drop_index("uq_geo_log_visit_idempotency", table_name="geo_verification_logs")
    op.drop_column("geo_verification_logs", "verification_type")
    sa.Enum(name="geo_verification_type_enum").drop(op.get_bind(), checkfirst=True)
