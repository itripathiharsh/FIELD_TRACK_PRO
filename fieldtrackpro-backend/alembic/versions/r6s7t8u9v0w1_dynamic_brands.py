"""dynamic brands master entity and relationships

Revision ID: r6s7t8u9v0w1
Revises: q5r6s7t8u9v0
Create Date: 2026-08-31 19:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "r6s7t8u9v0w1"
down_revision: Union[str, None] = "q5r6s7t8u9v0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create brands table
    op.create_table(
        "brands",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("normalized_name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("normalized_name", name="uq_brands_normalized_name"),
    )
    op.create_index("ix_brands_normalized_name", "brands", ["normalized_name"])

    # 2. Add brand_id column to customer_brands and payment_brand_allocations
    op.add_column(
        "customer_brands",
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("brands.id", ondelete="RESTRICT"), nullable=True),
    )
    op.create_index("ix_customer_brands_brand_id", "customer_brands", ["brand_id"])

    op.add_column(
        "payment_brand_allocations",
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("brands.id", ondelete="RESTRICT"), nullable=True),
    )
    op.create_index("ix_payment_brand_allocations_brand_id", "payment_brand_allocations", ["brand_id"])

    # 3. Seed initial master brands (strictly excluding non-business brand names like Lund)
    op.execute(
        """
        INSERT INTO brands (id, name, normalized_name, is_active, created_at, updated_at)
        VALUES 
            (gen_random_uuid(), 'USHA', 'usha', true, now(), now()),
            (gen_random_uuid(), 'Zebronics', 'zebronics', true, now(), now()),
            (gen_random_uuid(), 'VU', 'vu', true, now(), now()),
            (gen_random_uuid(), 'Havells', 'havells', true, now(), now()),
            (gen_random_uuid(), 'Finolex', 'finolex', true, now(), now()),
            (gen_random_uuid(), 'Anchor', 'anchor', true, now(), now())
        ON CONFLICT (normalized_name) DO NOTHING;
        """
    )

    # 4. Insert any other existing distinct brands from customer_brands, invoices, and payment allocations
    op.execute(
        """
        INSERT INTO brands (id, name, normalized_name, is_active, created_at, updated_at)
        SELECT 
            gen_random_uuid(),
            TRIM(source_brand.brand),
            LOWER(TRIM(source_brand.brand)),
            true,
            now(),
            now()
        FROM (
            SELECT DISTINCT brand FROM customer_brands WHERE brand IS NOT NULL AND TRIM(brand) != ''
            UNION
            SELECT DISTINCT brand FROM invoices WHERE brand IS NOT NULL AND TRIM(brand) != ''
            UNION
            SELECT DISTINCT brand FROM customer_requirements WHERE brand IS NOT NULL AND TRIM(brand) != ''
        ) AS source_brand
        WHERE LOWER(TRIM(source_brand.brand)) != 'lund'
        ON CONFLICT (normalized_name) DO NOTHING;
        """
    )

    # 5. Backfill brand_id in customer_brands and payment_brand_allocations
    op.execute(
        """
        UPDATE customer_brands cb
        SET brand_id = b.id
        FROM brands b
        WHERE LOWER(TRIM(cb.brand)) = b.normalized_name;
        """
    )
    op.execute(
        """
        UPDATE payment_brand_allocations pba
        SET brand_id = b.id
        FROM brands b
        WHERE LOWER(TRIM(pba.brand)) = b.normalized_name;
        """
    )


def downgrade() -> None:
    op.drop_index("ix_payment_brand_allocations_brand_id", table_name="payment_brand_allocations")
    op.drop_column("payment_brand_allocations", "brand_id")

    op.drop_index("ix_customer_brands_brand_id", table_name="customer_brands")
    op.drop_column("customer_brands", "brand_id")

    op.drop_index("ix_brands_normalized_name", table_name="brands")
    op.drop_table("brands")
