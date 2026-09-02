"""normalize brands and add financial brand_id

Revision ID: s8t9u0v1w2x3
Revises: r6s7t8u9v0w1
Create Date: 2026-09-02 02:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "s8t9u0v1w2x3"
down_revision: Union[str, None] = "r6s7t8u9v0w1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add brand_id to outlet_financial_snapshots
    op.add_column(
        "outlet_financial_snapshots",
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_outlet_financial_snapshots_brand_id",
        "outlet_financial_snapshots",
        ["brand_id"],
    )

    # 2. Add brand_id to invoices
    op.add_column(
        "invoices",
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index("ix_invoices_brand_id", "invoices", ["brand_id"])

    # 3. Ensure master brands exist (USHA, Zebronics, VU)
    op.execute(
        """
        INSERT INTO brands (id, name, normalized_name, is_active, created_at, updated_at)
        VALUES 
            (gen_random_uuid(), 'USHA', 'usha', true, now(), now()),
            (gen_random_uuid(), 'Zebronics', 'zebronics', true, now(), now()),
            (gen_random_uuid(), 'VU', 'vu', true, now(), now())
        ON CONFLICT (normalized_name) DO NOTHING;
        """
    )

    # 4. Normalize historical outlet_financial_snapshots records
    op.execute(
        """
        UPDATE outlet_financial_snapshots
        SET brand = 'Zebronics',
            brand_id = (SELECT id FROM brands WHERE normalized_name = 'zebronics' LIMIT 1)
        WHERE LOWER(TRIM(brand)) IN ('zbr', 'zebronics')
        """
    )

    op.execute(
        """
        UPDATE outlet_financial_snapshots
        SET brand = 'USHA',
            brand_id = (SELECT id FROM brands WHERE normalized_name = 'usha' LIMIT 1)
        WHERE LOWER(TRIM(brand)) IN ('usha')
        """
    )

    op.execute(
        """
        UPDATE outlet_financial_snapshots
        SET brand = 'VU',
            brand_id = (SELECT id FROM brands WHERE normalized_name = 'vu' LIMIT 1)
        WHERE LOWER(TRIM(brand)) IN ('vu')
        """
    )

    op.execute(
        """
        UPDATE outlet_financial_snapshots ofs
        SET brand_id = b.id,
            brand = b.name
        FROM brands b
        WHERE ofs.brand_id IS NULL AND LOWER(TRIM(ofs.brand)) = b.normalized_name
        """
    )

    # 5. Normalize invoices
    op.execute(
        """
        UPDATE invoices
        SET brand = 'Zebronics',
            brand_id = (SELECT id FROM brands WHERE normalized_name = 'zebronics' LIMIT 1)
        WHERE LOWER(TRIM(brand)) IN ('zbr', 'zebronics')
        """
    )

    op.execute(
        """
        UPDATE invoices
        SET brand = 'USHA',
            brand_id = (SELECT id FROM brands WHERE normalized_name = 'usha' LIMIT 1)
        WHERE LOWER(TRIM(brand)) IN ('usha')
        """
    )

    op.execute(
        """
        UPDATE invoices
        SET brand = 'VU',
            brand_id = (SELECT id FROM brands WHERE normalized_name = 'vu' LIMIT 1)
        WHERE LOWER(TRIM(brand)) IN ('vu')
        """
    )

    op.execute(
        """
        UPDATE invoices inv
        SET brand_id = b.id,
            brand = b.name
        FROM brands b
        WHERE inv.brand_id IS NULL AND inv.brand IS NOT NULL AND LOWER(TRIM(inv.brand)) = b.normalized_name
        """
    )

    # 6. Normalize payment_brand_allocations
    op.execute(
        """
        UPDATE payment_brand_allocations
        SET brand = 'Zebronics',
            brand_id = (SELECT id FROM brands WHERE normalized_name = 'zebronics' LIMIT 1)
        WHERE LOWER(TRIM(brand)) IN ('zbr', 'zebronics')
        """
    )

    op.execute(
        """
        UPDATE payment_brand_allocations
        SET brand = 'USHA',
            brand_id = (SELECT id FROM brands WHERE normalized_name = 'usha' LIMIT 1)
        WHERE LOWER(TRIM(brand)) IN ('usha')
        """
    )

    op.execute(
        """
        UPDATE payment_brand_allocations
        SET brand = 'VU',
            brand_id = (SELECT id FROM brands WHERE normalized_name = 'vu' LIMIT 1)
        WHERE LOWER(TRIM(brand)) IN ('vu')
        """
    )

    op.execute(
        """
        UPDATE payment_brand_allocations pba
        SET brand_id = b.id,
            brand = b.name
        FROM brands b
        WHERE pba.brand_id IS NULL AND LOWER(TRIM(pba.brand)) = b.normalized_name
        """
    )

    # 7. Normalize customer_brands
    op.execute(
        """
        UPDATE customer_brands
        SET brand = 'Zebronics',
            brand_id = (SELECT id FROM brands WHERE normalized_name = 'zebronics' LIMIT 1)
        WHERE LOWER(TRIM(brand)) IN ('zbr', 'zebronics')
        """
    )

    op.execute(
        """
        UPDATE customer_brands
        SET brand = 'USHA',
            brand_id = (SELECT id FROM brands WHERE normalized_name = 'usha' LIMIT 1)
        WHERE LOWER(TRIM(brand)) IN ('usha')
        """
    )

    op.execute(
        """
        UPDATE customer_brands
        SET brand = 'VU',
            brand_id = (SELECT id FROM brands WHERE normalized_name = 'vu' LIMIT 1)
        WHERE LOWER(TRIM(brand)) IN ('vu')
        """
    )

    op.execute(
        """
        UPDATE customer_brands cb
        SET brand_id = b.id,
            brand = b.name
        FROM brands b
        WHERE cb.brand_id IS NULL AND LOWER(TRIM(cb.brand)) = b.normalized_name
        """
    )

    # 8. Normalize customer_requirements
    op.execute(
        """
        UPDATE customer_requirements
        SET brand = 'Zebronics'
        WHERE LOWER(TRIM(brand)) IN ('zbr', 'zebronics')
        """
    )

    op.execute(
        """
        UPDATE customer_requirements
        SET brand = 'USHA'
        WHERE LOWER(TRIM(brand)) IN ('usha')
        """
    )

    op.execute(
        """
        UPDATE customer_requirements
        SET brand = 'VU'
        WHERE LOWER(TRIM(brand)) IN ('vu')
        """
    )


def downgrade() -> None:
    op.drop_index("ix_invoices_brand_id", table_name="invoices")
    op.drop_column("invoices", "brand_id")

    op.drop_index(
        "ix_outlet_financial_snapshots_brand_id",
        table_name="outlet_financial_snapshots",
    )
    op.drop_column("outlet_financial_snapshots", "brand_id")
