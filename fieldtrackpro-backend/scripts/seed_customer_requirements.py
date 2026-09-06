import asyncio
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.user import User
from app.models.visit import Visit
from app.models.customer_requirement import CustomerRequirement


async def seed_requirements():
    async with AsyncSessionLocal() as session:
        # Check existing count
        existing = (await session.execute(select(CustomerRequirement))).scalars().all()
        if existing:
            print(f"Found {len(existing)} existing customer requirements. Cleaning up before seeding fresh data...")
            for req in existing:
                await session.delete(req)
            await session.commit()

        # Find Users
        users_by_email = {}
        users = (await session.execute(select(User))).scalars().all()
        for u in users:
            users_by_email[u.email] = u

        admin_user = users_by_email.get("admin@fieldtrack.test")
        neeraj_user = users_by_email.get("neeraj.rajput@sgrgservices.com")
        sahil_user = users_by_email.get("sahil.verma@sgrgservices.com")
        raunak_user = users_by_email.get("raunak.sharma@sgrgservices.com")
        amit_user = users_by_email.get("amit.jaiswal@sgrgservices.com")
        sandeep_user = users_by_email.get("sandeep.mishra@sgrgservices.com")
        manish_user = users_by_email.get("manish.awasthi@sgrgservices.com")

        # Find Customers
        all_customers = (await session.execute(select(Customer))).scalars().all()
        cust_by_key = {}
        for c in all_customers:
            if c.outlet_code:
                cust_by_key[c.outlet_code] = c
            if c.name:
                cust_by_key[c.name] = c

        baba_mobiles = cust_by_key.get("Baba Mobiles (OPPO)") or cust_by_key.get("Baba Mobiles (UPDD639850)")
        om_rudra = cust_by_key.get("UPDD661818") or cust_by_key.get("Om Rudra Mobiles Shop (UPDD661818)")
        aradhya = cust_by_key.get("UPDD00680324") or cust_by_key.get("Aradhya Enterprises [UPDD00680324]")
        rizwan = cust_by_key.get("UPDD656578") or cust_by_key.get("Rizwan Mobile Hub [UPDD656578]")
        samyak = cust_by_key.get("UPDD654096") or cust_by_key.get("Samyak Communication (UPDD654096)")
        d_mobile = cust_by_key.get("UPDD667891") or cust_by_key.get("D Mobile Company (UPDD667891)")

        # Find Sahil's visit
        sahil_visit = None
        if baba_mobiles:
            sahil_visit = (await session.execute(
                select(Visit).where(Visit.customer_id == baba_mobiles.id)
            )).scalars().first()

        reqs_to_create = [
            # 1. PENDING - Sahil Verma at Baba Mobiles
            CustomerRequirement(
                id=uuid.uuid4(),
                customer_id=baba_mobiles.id,
                visit_id=sahil_visit.id if sahil_visit else None,
                brand="Oppo",
                requirement_type="Stock Replenishment",
                product_details="Oppo Reno 11 Pro 5G (12GB/256GB - Pearl White & Rock Grey)",
                quantity=15,
                expected_value=Decimal("585000.00"),
                follow_up_date=date(2026, 9, 12),
                notes="Customer reports surge in customer inquiries. Urgent dispatch requested before the weekend.",
                status="PENDING",
                created_by=sahil_user.id if sahil_user else admin_user.id,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
            # 2. PENDING - Raunak Sharma at Om Rudra Mobiles
            CustomerRequirement(
                id=uuid.uuid4(),
                customer_id=om_rudra.id,
                brand="Samsung",
                requirement_type="New Model Launch Display",
                product_details="Samsung Galaxy A55 5G & A35 5G Display Stock + In-shop Counter Top Acrylic Standee",
                quantity=20,
                expected_value=Decimal("620000.00"),
                follow_up_date=date(2026, 9, 15),
                notes="Dealer wants promotional standee and dummy display demo units alongside primary order.",
                status="PENDING",
                created_by=raunak_user.id if raunak_user else admin_user.id,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
            # 3. APPROVED - Amit Jaiswal at Aradhya Enterprises (Decided by Neeraj Rajput)
            CustomerRequirement(
                id=uuid.uuid4(),
                customer_id=aradhya.id,
                brand="Philips",
                requirement_type="Bulk Festival Booking",
                product_details="Philips LED Smart Series 43-inch & 50-inch 4K UHD TVs",
                quantity=25,
                expected_value=Decimal("750000.00"),
                follow_up_date=date(2026, 9, 8),
                notes="Festive pre-booking for local electronics bazaar.",
                status="APPROVED",
                approved_quantity=25,
                approved_value=Decimal("750000.00"),
                admin_notes="Approved by Sales Manager. Dispatch allocated from Kanpur central warehouse.",
                decided_by=neeraj_user.id if neeraj_user else admin_user.id,
                decided_at=datetime(2026, 9, 5, 14, 30, tzinfo=timezone.utc),
                created_by=amit_user.id if amit_user else admin_user.id,
                created_at=datetime(2026, 9, 4, 11, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 9, 5, 14, 30, tzinfo=timezone.utc),
            ),
            # 4. PARTIALLY_APPROVED - Sandeep Mishra at Rizwan Mobile Hub (Decided by Super Admin)
            CustomerRequirement(
                id=uuid.uuid4(),
                customer_id=rizwan.id,
                brand="Zebronics",
                requirement_type="Accessories Stock Expansion",
                product_details="Zebronics Soundbars (Zeb-Juke Bar 9500) & BT Wireless Neckbands",
                quantity=40,
                expected_value=Decimal("240000.00"),
                follow_up_date=date(2026, 9, 10),
                notes="Dealer requesting credit term extension for accessory bundle.",
                status="PARTIALLY_APPROVED",
                approved_quantity=25,
                approved_value=Decimal("150000.00"),
                admin_notes="Partially approved. Soundbar quota capped at 25 units until outstanding July ledger balance is settled.",
                decided_by=admin_user.id,
                decided_at=datetime(2026, 9, 5, 16, 15, tzinfo=timezone.utc),
                created_by=sandeep_user.id if sandeep_user else admin_user.id,
                created_at=datetime(2026, 9, 4, 15, 30, tzinfo=timezone.utc),
                updated_at=datetime(2026, 9, 5, 16, 15, tzinfo=timezone.utc),
            ),
            # 5. REJECTED - Manish Awasthi at Samyak Communication (Decided by Neeraj Rajput)
            CustomerRequirement(
                id=uuid.uuid4(),
                customer_id=samyak.id,
                brand="VU",
                requirement_type="Credit Limit Extension Request",
                product_details="VU Masterpiece Glo 55-inch QLED TVs",
                quantity=10,
                expected_value=Decimal("480000.00"),
                follow_up_date=date(2026, 9, 7),
                notes="Dealer asking for 45-day credit extension without security cheque.",
                status="REJECTED",
                admin_notes="Rejected per company credit policy. Overdue balance exceeds ₹3.5 Lakhs across 60+ days aging.",
                decided_by=neeraj_user.id if neeraj_user else admin_user.id,
                decided_at=datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc),
                created_by=manish_user.id if manish_user else admin_user.id,
                created_at=datetime(2026, 9, 5, 17, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc),
            ),
            # 6. PENDING - Sahil Verma at D Mobile Company
            CustomerRequirement(
                id=uuid.uuid4(),
                customer_id=d_mobile.id,
                brand="USHA",
                requirement_type="Consumer Appliances Seasonal Order",
                product_details="USHA Striker Galaxy High Speed Ceiling Fans (1200mm)",
                quantity=50,
                expected_value=Decimal("135000.00"),
                follow_up_date=date(2026, 9, 18),
                notes="Dealer wants delivery in two staggered batches next week.",
                status="PENDING",
                created_by=sahil_user.id if sahil_user else admin_user.id,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
        ]

        session.add_all(reqs_to_create)
        await session.commit()
        print(f"Successfully seeded {len(reqs_to_create)} Customer Requirements!")
        for r in reqs_to_create:
            print(f"- [{r.status}] {r.brand} | {r.product_details[:40]}... | Qty: {r.quantity} | Val: INR {r.expected_value}")


if __name__ == "__main__":
    asyncio.run(seed_requirements())
