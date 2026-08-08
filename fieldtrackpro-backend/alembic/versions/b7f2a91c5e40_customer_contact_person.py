"""customer contact_person, users identity check

Repairs FT-013 and FT-034.

FT-013  The admin form labelled a field "Contact Person" but wrote it to
        customers.contact_number, which is varchar(20). Any realistic full name
        overflowed and produced an unhandled HTTP 500. The two concerns are now
        separate columns.

FT-034  users had no constraint requiring at least one login identity. The
        service layer checked it, but nothing stopped a direct insert (or a
        future code path) from creating an unusable account.

Revision ID: b7f2a91c5e40
Revises: a1c4e77b9d21
Create Date: 2026-08-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7f2a91c5e40"
down_revision: Union[str, Sequence[str], None] = "a1c4e77b9d21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- FT-013 ------------------------------------------------------------
    op.add_column(
        "customers",
        sa.Column("contact_person", sa.String(length=150), nullable=True),
    )

    # Existing rows where contact_number clearly holds a person's name rather
    # than a phone number: move the value into the new column. A phone number
    # is treated as a value made only of digits, spaces and +-()/. characters.
    op.execute(
        """
        UPDATE customers
        SET contact_person = contact_number,
            contact_number = ''
        WHERE contact_number !~ '^[0-9+()\\-.\\s/]+$'
        """
    )

    # --- FT-034 ------------------------------------------------------------
    # Guard against accounts with no way to log in. Written as NOT VALID first
    # so the migration cannot fail on pre-existing data, then validated; if
    # legacy rows violate it the validation error is explicit rather than the
    # constraint being silently skipped.
    op.execute(
        """
        ALTER TABLE users
        ADD CONSTRAINT ck_users_identity_present
        CHECK (email IS NOT NULL OR mobile_number IS NOT NULL) NOT VALID
        """
    )
    op.execute("ALTER TABLE users VALIDATE CONSTRAINT ck_users_identity_present")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_identity_present")

    op.execute(
        """
        UPDATE customers
        SET contact_number = contact_person
        WHERE (contact_number IS NULL OR contact_number = '')
          AND contact_person IS NOT NULL
        """
    )
    op.drop_column("customers", "contact_person")
