import asyncio
import httpx
from datetime import datetime, timezone, timedelta
from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.employee import Employee
from app.models.customer import Customer
from app.models.visit import Visit, VisitStatus

IST = timezone(timedelta(hours=5, minutes=30))
PROD_API_URL = "https://fieldtrackpro-backend-s7hs.onrender.com"

# Target Coordinates (Current Device GPS Location)
LAT = 26.734115
LON = 80.943602
GEOFENCE_RADIUS = 500 # 500 meters to ensure easy checkin

async def assign_local_db():
    print("\n--- Assigning in Local Database ---")
    try:
        async with AsyncSessionLocal() as session:
            # 1. Fetch Users/Employees
            users_stmt = select(User, Employee).outerjoin(Employee, Employee.user_id == User.id).where(
                User.email.in_(["imharshofficial322@gmail.com", "sahil.verma@sgrgservices.com", "admin@fieldtrack.test"])
            )
            results = (await session.execute(users_stmt)).all()
            
            admin_user = None
            harsh_emp = None
            sahil_emp = None
            
            for user, emp in results:
                if user.email == "admin@fieldtrack.test":
                    admin_user = user
                if user.email == "imharshofficial322@gmail.com":
                    harsh_emp = emp
                if user.email == "sahil.verma@sgrgservices.com":
                    sahil_emp = emp
            
            created_by_id = admin_user.id if admin_user else (results[0][0].id if results else None)
            
            # Target employees to assign visit to
            target_employees = [e for e in [harsh_emp, sahil_emp] if e is not None]
            if not target_employees:
                # Get first available employee
                all_emps = (await session.execute(select(Employee))).scalars().all()
                if all_emps:
                    target_employees = [all_emps[0]]
            
            # 2. Create or update Customer Outlet at Current Location
            location_wkt = WKTElement(f"POINT({LON} {LAT})", srid=4326)
            cust_stmt = select(Customer).where(Customer.name == "Current Location Test Outlet")
            customer = (await session.execute(cust_stmt)).scalars().first()
            if not customer:
                customer = Customer(
                    name="Current Location Test Outlet",
                    contact_number="9839011001",
                    contact_person="Harsh / Store Manager",
                    address="Current GPS Location (Telibagh / Lucknow)",
                    location=location_wkt,
                    geofence_radius_m=GEOFENCE_RADIUS,
                    location_status="VERIFIED",
                    outlet_code="CURR-GPS-001",
                    created_by=created_by_id
                )
                session.add(customer)
                await session.flush()
                print(f"Created Customer: {customer.name} (ID: {customer.id})")
            else:
                customer.location = location_wkt
                customer.geofence_radius_m = GEOFENCE_RADIUS
                customer.location_status = "VERIFIED"
                await session.flush()
                print(f"Updated Customer: {customer.name} (ID: {customer.id})")

            # 3. Schedule Visit for 30th August 2026
            # Current date is 30th August 2026
            scheduled_time = datetime(2026, 8, 30, 10, 0, 0, tzinfo=IST).astimezone(timezone.utc)
            
            for emp in target_employees:
                # Check if existing pending visit
                visit_stmt = select(Visit).where(
                    Visit.customer_id == customer.id,
                    Visit.employee_id == emp.id,
                    Visit.status == VisitStatus.PENDING
                )
                existing_visit = (await session.execute(visit_stmt)).scalars().first()
                if existing_visit:
                    existing_visit.scheduled_at = scheduled_time
                    print(f"Updated existing pending Visit ID {existing_visit.id} for Employee {emp.full_name} ({emp.employee_code})")
                else:
                    new_visit = Visit(
                        customer_id=customer.id,
                        employee_id=emp.id,
                        scheduled_at=scheduled_time,
                        status=VisitStatus.PENDING,
                        notes="Live testing visit for GPS Check-in and Check-out at current location.",
                        created_by=created_by_id
                    )
                    session.add(new_visit)
                    await session.flush()
                    print(f"Created new Visit ID {new_visit.id} for Employee {emp.full_name} ({emp.employee_code})")

            await session.commit()
            print("Local DB update successfully committed!")
    except Exception as e:
        print(f"Local DB error: {e}")

async def assign_production_render():
    print("\n--- Assigning in Production Render Backend ---")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Login as Admin
            login_resp = await client.post(f"{PROD_API_URL}/api/v1/auth/login", json={
                "email": "admin@fieldtrack.test",
                "password": "AdminPass123!"
            })
            if login_resp.status_code != 200:
                print(f"Prod login failed: {login_resp.status_code} - {login_resp.text}")
                return
            token = login_resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            
            # Fetch employees
            emps_resp = await client.get(f"{PROD_API_URL}/api/v1/employees", headers=headers)
            employees = emps_resp.json() if emps_resp.status_code == 200 else []
            print(f"Found {len(employees)} employees in production.")
            
            # Find Harsh or Sahil or all active employees
            target_emp_ids = []
            for emp in employees:
                if emp.get("employee_code") in ["ADM001", "11001", "11002"] or "Harsh" in emp.get("full_name", "") or "Sahil" in emp.get("full_name", ""):
                    target_emp_ids.append(emp)
            
            if not target_emp_ids and employees:
                target_emp_ids = [employees[0]]
            
            # Check or create customer
            custs_resp = await client.get(f"{PROD_API_URL}/api/v1/customers?search=Current%20Location", headers=headers)
            customer_id = None
            if custs_resp.status_code == 200 and custs_resp.json():
                customer_id = custs_resp.json()[0]["id"]
                # Update location and geofence
                upd_resp = await client.put(f"{PROD_API_URL}/api/v1/customers/{customer_id}", headers=headers, json={
                    "latitude": LAT,
                    "longitude": LON,
                    "geofence_radius_m": GEOFENCE_RADIUS,
                    "address": "Current GPS Location (Telibagh / Lucknow)"
                })
                print(f"Updated prod customer {customer_id}: Status {upd_resp.status_code}")
            else:
                create_resp = await client.post(f"{PROD_API_URL}/api/v1/customers", headers=headers, json={
                    "name": "Current Location Test Outlet",
                    "outlet_code": "CURR-GPS-001",
                    "contact_person": "Harsh / Store Manager",
                    "contact_number": "9839011001",
                    "address": "Current GPS Location (Telibagh / Lucknow)",
                    "latitude": LAT,
                    "longitude": LON,
                    "geofence_radius_m": GEOFENCE_RADIUS
                })
                if create_resp.status_code in [200, 201]:
                    customer_id = create_resp.json()["id"]
                    print(f"Created prod customer {customer_id}")
                else:
                    print(f"Create prod customer failed: {create_resp.status_code} - {create_resp.text}")
                    # Try fetching all customers
                    all_c = await client.get(f"{PROD_API_URL}/api/v1/customers?limit=1", headers=headers)
                    if all_c.status_code == 200 and all_c.json():
                        customer_id = all_c.json()[0]["id"]
                        print(f"Using fallback customer {customer_id}")

            if customer_id:
                # Schedule visit for 30th August 2026
                scheduled_iso = datetime(2026, 8, 30, 10, 0, 0, tzinfo=IST).isoformat()
                for emp in target_emp_ids:
                    emp_id = emp["id"]
                    visit_payload = {
                        "customer_id": customer_id,
                        "employee_id": emp_id,
                        "scheduled_at": scheduled_iso,
                        "notes": "Live testing visit for GPS Check-in and Check-out at current location."
                    }
                    visit_resp = await client.post(f"{PROD_API_URL}/api/v1/visits", headers=headers, json=visit_payload)
                    print(f"Scheduled Prod Visit for {emp.get('full_name')} ({emp.get('employee_code')}): Status {visit_resp.status_code} -> {visit_resp.text[:100]}")

    except Exception as e:
        print(f"Production Render error: {e}")

async def main():
    await assign_local_db()
    await assign_production_render()

if __name__ == "__main__":
    asyncio.run(main())
