import requests
from datetime import datetime, timezone, timedelta
from geoalchemy2.elements import WKTElement
from sqlalchemy import select
import asyncio

from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.employee import Employee
from app.models.customer import Customer
from app.models.visit import Visit, VisitStatus

IST = timezone(timedelta(hours=5, minutes=30))
PROD_API_URL = "https://fieldtrackpro-backend-s7hs.onrender.com"
LOCAL_API_URL = "http://localhost:8000"

LAT = 26.734115
LON = 80.943602
GEOFENCE_RADIUS = 500

print("="*60)
print("CREATING TEST VISIT #2 FOR AUGUST 30TH (Local & Prod)")
print("="*60)

async def create_local_visit():
    print("\n--- 1. Creating on Local Database ---")
    async with AsyncSessionLocal() as session:
        # Find user Harsh
        user_stmt = select(User, Employee).outerjoin(Employee, Employee.user_id == User.id).where(
            User.email == "imharshofficial322@gmail.com"
        )
        row = (await session.execute(user_stmt)).first()
        if not row or not row[1]:
            print("Harsh employee not found on local DB!")
            return
        user, employee = row

        # Admin user
        admin = (await session.execute(select(User).where(User.email == "admin@fieldtrack.test"))).scalars().first()
        created_by_id = admin.id if admin else user.id

        # Customer #2 at current location
        location_wkt = WKTElement(f"POINT({LON} {LAT})", srid=4326)
        cust_stmt = select(Customer).where(Customer.outlet_code == "HARSH-TEST-02")
        customer = (await session.execute(cust_stmt)).scalars().first()
        if not customer:
            customer = Customer(
                name="Harsh Live Test Outlet #2",
                contact_number="9565249244",
                contact_person="Harsh Vardhan Tripathi",
                address="Telibagh, Lucknow (Current GPS Location #2)",
                location=location_wkt,
                geofence_radius_m=GEOFENCE_RADIUS,
                location_status="VERIFIED",
                outlet_code="HARSH-TEST-02",
                created_by=created_by_id
            )
            session.add(customer)
            await session.flush()
            print(f"Created Local Customer: {customer.name} (ID: {customer.id})")
        else:
            customer.location = location_wkt
            customer.geofence_radius_m = GEOFENCE_RADIUS
            customer.location_status = "VERIFIED"
            await session.flush()
            print(f"Updated Local Customer: {customer.name} (ID: {customer.id})")

        # Scheduled time: Today 12:30 PM IST (to avoid 60min conflict with 10:00 AM visit)
        scheduled_time = datetime(2026, 8, 30, 12, 30, 0, tzinfo=IST).astimezone(timezone.utc)

        new_visit = Visit(
            customer_id=customer.id,
            employee_id=employee.id,
            scheduled_at=scheduled_time,
            status=VisitStatus.PENDING,
            notes="Second live test visit for GPS Check-in, photo receipt, and Check-out.",
            created_by=created_by_id
        )
        session.add(new_visit)
        await session.commit()
        print(f"SUCCESS: Local Visit Scheduled: ID {new_visit.id} for {employee.full_name} at {scheduled_time} UTC")

def create_prod_visit():
    print("\n--- 2. Creating on Production Render Backend ---")
    try:
        r_admin = requests.post(f"{PROD_API_URL}/api/v1/auth/login", json={
            "email": "admin@fieldtrack.test",
            "password": "AdminPass123!"
        }, timeout=30)
        if r_admin.status_code != 200:
            print(f"Prod admin login failed: {r_admin.status_code}")
            return
        token = r_admin.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create or get customer #2
        cust_payload = {
            "name": "Harsh Live Test Outlet #2",
            "outlet_code": "HARSH-TEST-02",
            "contact_person": "Harsh Vardhan Tripathi",
            "contact_number": "9565249244",
            "address": "Telibagh, Lucknow (Current GPS Location #2)",
            "location": {
                "latitude": LAT,
                "longitude": LON
            },
            "geofence_radius_m": GEOFENCE_RADIUS,
            "location_status": "VERIFIED"
        }
        r_c = requests.post(f"{PROD_API_URL}/api/v1/customers", json=cust_payload, headers=headers, timeout=30)
        if r_c.status_code in [200, 201]:
            customer_id = r_c.json()["id"]
            print(f"Created Prod Customer: {customer_id}")
        else:
            r_search = requests.get(f"{PROD_API_URL}/api/v1/customers?search=HARSH-TEST-02", headers=headers, timeout=30).json()
            items = r_search.get("items", []) if isinstance(r_search, dict) else r_search
            customer_id = items[0]["id"]
            print(f"Using existing Prod Customer: {customer_id}")

        # 2. Find Harsh Employee ID
        emps = requests.get(f"{PROD_API_URL}/api/v1/employees?search=Harsh", headers=headers, timeout=30).json()
        emp_items = emps.get("items", []) if isinstance(emps, dict) else emps
        harsh_emp_id = emp_items[0]["id"]

        # 3. Schedule Visit for Harsh at 12:30 PM IST (07:00 UTC)
        scheduled_iso = datetime(2026, 8, 30, 12, 30, 0, tzinfo=IST).isoformat()
        visit_payload = {
            "customer_id": customer_id,
            "employee_id": harsh_emp_id,
            "scheduled_at": scheduled_iso,
            "notes": "Second live test visit for GPS Check-in, photo receipt, and Check-out."
        }
        r_v = requests.post(f"{PROD_API_URL}/api/v1/visits", json=visit_payload, headers=headers, timeout=30)
        print(f"Prod Visit Schedule Status: {r_v.status_code} -> {r_v.text[:120]}")

    except Exception as e:
        print(f"Prod create visit error: {e}")

async def main():
    await create_local_visit()
    create_prod_visit()

if __name__ == "__main__":
    asyncio.run(main())
