import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.config import settings

async def main():
    db_url = settings.migration_database_url or settings.database_url
    engine = create_async_engine(db_url, echo=True)
    
    statements = [
        # 1. Create brands table
        """
        CREATE TABLE IF NOT EXISTS brands (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(100) NOT NULL,
            normalized_name VARCHAR(100) NOT NULL UNIQUE,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_brands_normalized_name ON brands(normalized_name)",
        
        # 2. Add brand_id column
        "ALTER TABLE customer_brands ADD COLUMN IF NOT EXISTS brand_id UUID REFERENCES brands(id) ON DELETE RESTRICT",
        "CREATE INDEX IF NOT EXISTS ix_customer_brands_brand_id ON customer_brands(brand_id)",
        
        "ALTER TABLE payment_brand_allocations ADD COLUMN IF NOT EXISTS brand_id UUID REFERENCES brands(id) ON DELETE RESTRICT",
        "CREATE INDEX IF NOT EXISTS ix_payment_brand_allocations_brand_id ON payment_brand_allocations(brand_id)",
        
        # 3. Seed initial master brands
        """
        INSERT INTO brands (id, name, normalized_name, is_active, created_at, updated_at)
        VALUES 
            (gen_random_uuid(), 'USHA', 'usha', true, now(), now()),
            (gen_random_uuid(), 'Zebronics', 'zebronics', true, now(), now()),
            (gen_random_uuid(), 'VU', 'vu', true, now(), now()),
            (gen_random_uuid(), 'Havells', 'havells', true, now(), now()),
            (gen_random_uuid(), 'Finolex', 'finolex', true, now(), now()),
            (gen_random_uuid(), 'Anchor', 'anchor', true, now(), now())
        ON CONFLICT (normalized_name) DO NOTHING
        """,
        
        # 4. Insert existing distinct brands
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
        ON CONFLICT (normalized_name) DO NOTHING
        """,
        
        # 5. Backfill brand_id
        """
        UPDATE customer_brands cb
        SET brand_id = b.id
        FROM brands b
        WHERE LOWER(TRIM(cb.brand)) = b.normalized_name AND cb.brand_id IS NULL
        """,
        
        """
        UPDATE payment_brand_allocations pba
        SET brand_id = b.id
        FROM brands b
        WHERE LOWER(TRIM(pba.brand)) = b.normalized_name AND pba.brand_id IS NULL
        """,
        
        # 6. Update alembic_version
        "UPDATE alembic_version SET version_num = 'r6s7t8u9v0w1'",
    ]
    
    async with engine.begin() as conn:
        for stmt in statements:
            await conn.execute(text(stmt))
        print("Brands migration successfully applied!")

    await engine.dispose()

if __name__ == '__main__':
    asyncio.run(main())
