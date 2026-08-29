import asyncio
from datetime import datetime, timezone, timedelta
from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from app.database import async_session_factory
from app.models.user import User
from app.models.employee import Employee
from app.models.customer import Customer
from app.models.visit import Visit, VisitStatus

IST = timezone(timedelta(hours=5, minutes=30))

async def main():
    async with async_session_factory() as session:
        # 1. Find Harsh's User and Employee record
        user_stmt = select(User).where(User.email == "imharshofficial322@gmail.com")
        user = (await session.execute(user_stmt)).scalars().first()
        if not user:
            print("Harsh user not found!")
            return

        emp_stmt = select(Employee).where(Employee.user_id == user.id)
        employee = (await session.execute(emp_stmt)).scalars().first()
        if not employee:
            print("Harsh employee profile not found!")
            return

        # 2. Find admin user to set as created_by
        admin_stmt = select(User).where(User.email == "admin@fieldtrack.test")
        admin = (await session.execute(admin_stmt)).scalars().first()
        created_by_id = admin.id if admin else user.id

        # 3. Create or update test customer at user's current GPS location: 26.734115, 80.943602
        lat = 26.734115
        lon = 80.943602
        location_wkt = WKTElement(f"POINT({lon} {lat})", srid=4326)

        cust_stmt = select(Customer).where(Customer.name == "Harsh Live Test Outlet")
        customer = (await session.execute(cust_stmt)).scalars().first()
        if not customer:
            customer = Customer(
                name="Harsh Live Test Outlet",
                contact_number="9565249244",
                contact_person="Harsh Vardhan Tripathi",
                address="Near Telibagh / Current Location, Lucknow",
                location=location_wkt,
                geofence_radius_m=300,
                location_status="VERIFIED",
                outlet_code="HARSH-GPS-001",
                created_by=created_by_id
            )
            session.add(customer)
            await session.flush()
            print(f"Created Customer: {customer.name} (ID: {customer.id})")
        else:
            customer.location = location_wkt
            customer.geofence_radius_m = 300
            customer.location_status = "VERIFIED"
            await session.flush()
            print(f"Updated Customer: {customer.name} (ID: {customer.id})")

        # 4. Schedule a visit for August 30, 2026 (Today IST)
        now_ist = datetime.now(IST)
        scheduled_time = datetime(2026, 8, 30, 10, 0, 0, tzinfo=IST).astimezone(timezone.utc)

        new_visit = Visit(
            customer_id=customer.id,
            employee_id=employee.id,
            scheduled_at=scheduled_time,
            status=VisitStatus.PENDING,
            notes="Live testing visit for GPS Check-in, signatures, orders and checkout.",
            created_by=created_by_id
        )
        session.add(new_visit)
        await session.commit()
        await session.refresh(new_visit)

        print(f"SUCCESS: Scheduled Visit {new_visit.id} for Harsh ({employee.full_name}) on {new_visit.scheduled_at} UTC!")

if __name__ == "__main__":
    asyncio.run(main())
