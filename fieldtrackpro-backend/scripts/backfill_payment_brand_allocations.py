import asyncio
import asyncpg
import re
from decimal import Decimal

BRAND_PATTERNS = [
    (re.compile(r"\b(philips|ph\b|ph\.)", re.IGNORECASE), "Philips"),
    (re.compile(r"\b(oppo)\b", re.IGNORECASE), "Oppo"),
    (re.compile(r"\b(usha)\b", re.IGNORECASE), "USHA"),
    (re.compile(r"\b(vu)\b", re.IGNORECASE), "VU"),
    (re.compile(r"\b(zebronics|zbr)\b", re.IGNORECASE), "Zebronics"),
]

BRAND_UUIDS = {
    "USHA": "1546a21e-0041-4de4-9767-a72e0fc5018c",
    "Zebronics": "0729ff27-2091-4c18-8278-38be0b9dbae8",
    "VU": "5378ee2b-4944-42e4-b08d-4f78f3fcfba2",
    "Oppo": "b2928229-28c8-4c29-b8c1-e40c407abff3",
    "Philips": "e17cb803-959a-43d6-b4fb-fe4c00f5c752",
}

def resolve_brand(cust_name: str, outlet_code: str | None) -> str:
    if outlet_code:
        u = outlet_code.strip().upper()
        if u.startswith("SGRGZBR"):
            return "Zebronics"
        if u.startswith("SGRGUS"):
            return "USHA"
        if u.startswith("SGRGVU"):
            return "VU"
        if u.startswith("UPDD"):
            return "Philips"
    if cust_name:
        for pattern, canonical in BRAND_PATTERNS:
            if pattern.search(cust_name):
                return canonical
        if "updd" in cust_name.lower():
            return "Philips"
    return "General"

async def backfill():
    conn = await asyncpg.connect("postgresql://fieldtrack_app:XcWG3aLw7s8mL75vrvl97aDZTSXbr4y6@127.0.0.1:5432/fieldtrackpro_dev")
    
    rows = await conn.fetch("""
        SELECT p.id, p.amount, c.name, c.outlet_code 
        FROM payments p 
        JOIN customers c ON p.customer_id = c.id 
        WHERE p.id NOT IN (SELECT payment_id FROM payment_brand_allocations)
    """)
    print(f"Found {len(rows)} payments without brand allocation.")
    
    counts = {}
    sums = {}
    async with conn.transaction():
        for r in rows:
            b = resolve_brand(r["name"], r["outlet_code"])
            b_uuid = BRAND_UUIDS.get(b)
            await conn.execute("""
                INSERT INTO payment_brand_allocations 
                    (id, payment_id, brand, brand_id, allocated_amount, created_at, updated_at)
                VALUES 
                    (gen_random_uuid(), $1, $2, $3::uuid, $4, now(), now())
                ON CONFLICT (payment_id, brand) 
                DO NOTHING
            """, r["id"], b, b_uuid, r["amount"])
            
            counts[b] = counts.get(b, 0) + 1
            sums[b] = sums.get(b, Decimal("0.00")) + r["amount"]
            
    print("\nBackfilled payment brand allocations:")
    for k in sorted(counts.keys()):
        print(f"  {k}: count={counts[k]}, sum={sums[k]:,.2f}")
        
    await conn.close()

if __name__ == "__main__":
    asyncio.run(backfill())
