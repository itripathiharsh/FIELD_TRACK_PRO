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
    (re.compile(r"\b(vivo)\b", re.IGNORECASE), "Vivo"),
    (re.compile(r"\b(samsung)\b", re.IGNORECASE), "Samsung"),
]

BRAND_UUIDS = {
    "USHA": "1546a21e-0041-4de4-9767-a72e0fc5018c",
    "Zebronics": "0729ff27-2091-4c18-8278-38be0b9dbae8",
    "VU": "5378ee2b-4944-42e4-b08d-4f78f3fcfba2",
    "Oppo": "b2928229-28c8-4c29-b8c1-e40c407abff3",
    "Philips": "e17cb803-959a-43d6-b4fb-fe4c00f5c752",
}

def resolve_brand(cust_name: str, outlet_code: str | None) -> str | None:
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
    return None

async def run_backfill():
    conn = await asyncpg.connect("postgresql://fieldtrack_app:XcWG3aLw7s8mL75vrvl97aDZTSXbr4y6@127.0.0.1:5432/fieldtrackpro_dev")
    
    rows = await conn.fetch("""
        SELECT i.id, i.amount, c.id as cust_id, c.name, c.outlet_code 
        FROM invoices i 
        JOIN customers c ON i.customer_id = c.id 
        WHERE i.brand IS NULL
    """)
    print(f"Found {len(rows)} invoices with NULL brand.")
    
    updated_counts = {}
    updated_amounts = {}
    
    async with conn.transaction():
        for r in rows:
            b = resolve_brand(r["name"], r["outlet_code"])
            if b and b in BRAND_UUIDS:
                b_uuid = BRAND_UUIDS[b]
                await conn.execute("""
                    UPDATE invoices 
                    SET brand = $1, brand_id = $2::uuid, updated_at = now() 
                    WHERE id = $3
                """, b, b_uuid, r["id"])
                
                # Check/add customer_brand
                cb_exists = await conn.fetchval("""
                    SELECT 1 FROM customer_brands 
                    WHERE customer_id = $1 AND brand = $2
                """, r["cust_id"], b)
                if not cb_exists:
                    await conn.execute("""
                        INSERT INTO customer_brands (id, customer_id, brand, brand_id, is_active, created_at, updated_at)
                        VALUES (gen_random_uuid(), $1, $2, $3::uuid, true, now(), now())
                        ON CONFLICT DO NOTHING
                    """, r["cust_id"], b, b_uuid)
                
                updated_counts[b] = updated_counts.get(b, 0) + 1
                updated_amounts[b] = updated_amounts.get(b, Decimal("0.00")) + r["amount"]
                
    print("\nBackfill results:")
    for b, cnt in sorted(updated_counts.items()):
        print(f"  {b}: {cnt} invoices, amount: {updated_amounts[b]:,.2f}")
        
    # Check remaining unbranded
    remaining_unbranded = await conn.fetchval("SELECT count(*) FROM invoices WHERE brand IS NULL")
    remaining_amount = await conn.fetchval("SELECT coalesce(sum(amount), 0) FROM invoices WHERE brand IS NULL")
    print(f"\nRemaining genuine unbranded invoices: {remaining_unbranded}, total: {remaining_amount:,.2f}")
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(run_backfill())
