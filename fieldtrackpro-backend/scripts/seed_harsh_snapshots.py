import asyncio
from decimal import Decimal
from datetime import date
from sqlalchemy import text
from app.database import AsyncSessionLocal

async def seed_snaps():
    async with AsyncSessionLocal() as session:
        # Fetch customers assigned to Harsh or visited by Harsh
        res = await session.execute(text("""
            SELECT DISTINCT c.id, c.name, c.territory_id, c.area_id
            FROM customers c
            JOIN employee_customer_assignments a ON a.customer_id = c.id
            JOIN employees e ON a.employee_id = e.id
            WHERE e.full_name ILIKE '%Harsh%'
        """))
        custs = res.fetchall()
        print(f"Provisioning financial snapshots for {len(custs)} Harsh outlets:")
        
        today = date.today()
        brands = ["Usha", "VU", "ZBR"]
        for idx, (cid, name, tid, aid) in enumerate(custs):
            b_name = brands[idx % len(brands)]
            # Check if snapshot already exists
            existing = (await session.execute(text("""
                SELECT id FROM outlet_financial_snapshots 
                WHERE customer_id = :cid
            """), {"cid": cid})).first()
            
            if not existing:
                await session.execute(text("""
                    INSERT INTO outlet_financial_snapshots (
                        id, customer_id, brand, snapshot_date,
                        sales, collection, market_outstanding,
                        bucket_lt_15, bucket_15_30, bucket_30_45,
                        bucket_45_60, bucket_60_75, bucket_75_90, bucket_gt_90,
                        created_at, updated_at
                    ) VALUES (
                        gen_random_uuid(), :cid, :brand, :sdate,
                        150000.00, 50000.00, 100000.00,
                        25000.00, 25000.00, 20000.00,
                        15000.00, 10000.00, 5000.00, 0.00,
                        now(), now()
                    )
                """), {
                    "cid": cid,
                    "brand": b_name,
                    "sdate": today,
                })
                print(f"  + Added snapshot for {name} ({b_name})")
            else:
                print(f"  = Snapshot already exists for {name}")
                
        await session.commit()
        print("Snapshots committed successfully!")

if __name__ == "__main__":
    asyncio.run(seed_snaps())
