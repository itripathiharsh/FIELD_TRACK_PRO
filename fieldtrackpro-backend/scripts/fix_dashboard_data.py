import asyncio
from sqlalchemy import text
from app.database import AsyncSessionLocal

async def fix():
    async with AsyncSessionLocal() as session:
        # 1. Fetch all Harsh employee IDs
        res = await session.execute(text("SELECT id, full_name, employee_code FROM employees WHERE full_name ILIKE '%Harsh%'"))
        harsh_emps = res.fetchall()
        print("Harsh employees:", harsh_emps)
        
        # 2. Fetch all customers Harsh visited or collected payment from
        res = await session.execute(text("""
            SELECT DISTINCT c.id, c.name, v.employee_id
            FROM customers c
            JOIN visits v ON v.customer_id = c.id
            JOIN employees e ON v.employee_id = e.id
            WHERE e.full_name ILIKE '%Harsh%'
        """))
        custs = res.fetchall()
        print(f"\nFound {len(custs)} customers visited by Harsh:")
        for cid, cname, empid in custs:
            print(f"  - {cname} (ID: {cid}, Emp: {empid})")
            # Assign in employee_customer_assignments if not exists
            admin_user = (await session.execute(text("SELECT id FROM users WHERE role = 'ADMIN' LIMIT 1"))).scalar()
            await session.execute(text("""
                INSERT INTO employee_customer_assignments (id, employee_id, customer_id, created_by, created_at)
                VALUES (gen_random_uuid(), :emp_id, :cust_id, :created_by, now())
                ON CONFLICT DO NOTHING
            """), {"emp_id": empid, "cust_id": cid, "created_by": admin_user})
        
        await session.commit()
        print("Customer assignments committed successfully!")

if __name__ == "__main__":
    asyncio.run(fix())
