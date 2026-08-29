import requests
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
PROD_API_URL = "https://fieldtrackpro-backend-s7hs.onrender.com"

# Target Coordinates (Current Device GPS Location)
LAT = 26.734115
LON = 80.943602
GEOFENCE_RADIUS = 500 # 500 meters

session = requests.Session()

# 1. Login as Admin
login_resp = session.post(f"{PROD_API_URL}/api/v1/auth/login", json={
    "email": "admin@fieldtrack.test",
    "password": "AdminPass123!"
}, timeout=90)

print(f"Prod Login: {login_resp.status_code}")
if login_resp.status_code == 200:
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    session.headers.update(headers)

    # 2. Get Employees
    emps_resp = session.get(f"{PROD_API_URL}/api/v1/employees?limit=100")
    print(f"Employees list: {emps_resp.status_code}")
    employees = emps_resp.json().get("items", []) if isinstance(emps_resp.json(), dict) else emps_resp.json()

    # Find Harsh, Sahil, or all active
    target_emps = []
    for emp in employees:
        name = emp.get("full_name", "")
        code = emp.get("employee_code", "")
        if "Harsh" in name or "Sahil" in name or code in ["11001", "ADM001"]:
            target_emps.append(emp)
    
    if not target_emps and employees:
        target_emps = employees[:3]
    
    print(f"Target employees: {[(e.get('full_name'), e.get('employee_code')) for e in target_emps]}")

    # 3. Create or update Customer at location
    # Search existing
    cust_resp = session.get(f"{PROD_API_URL}/api/v1/customers?limit=100")
    cust_items = cust_resp.json().get("items", []) if isinstance(cust_resp.json(), dict) else cust_resp.json()
    
    customer_id = None
    for c in cust_items:
        if "Current Location" in c.get("name", "") or "Harsh Live Test" in c.get("name", ""):
            customer_id = c["id"]
            # update
            session.put(f"{PROD_API_URL}/api/v1/customers/{customer_id}", json={
                "name": "Current Location Test Outlet",
                "latitude": LAT,
                "longitude": LON,
                "geofence_radius_m": GEOFENCE_RADIUS,
                "address": "Current GPS Location (Telibagh / Lucknow)",
                "location_status": "VERIFIED"
            })
            print(f"Updated customer {customer_id}")
            break
    
    if not customer_id:
        create_c = session.post(f"{PROD_API_URL}/api/v1/customers", json={
            "name": "Current Location Test Outlet",
            "outlet_code": "CURR-GPS-001",
            "contact_person": "Harsh / Store Manager",
            "contact_number": "9839011001",
            "address": "Current GPS Location (Telibagh / Lucknow)",
            "latitude": LAT,
            "longitude": LON,
            "geofence_radius_m": GEOFENCE_RADIUS,
            "location_status": "VERIFIED"
        })
        print(f"Create customer: {create_c.status_code}")
        if create_c.status_code in [200, 201]:
            customer_id = create_c.json()["id"]

    if customer_id:
        # Schedule visit for 30th August 2026
        scheduled_iso = datetime(2026, 8, 30, 10, 0, 0, tzinfo=IST).isoformat()
        for emp in target_emps:
            v_payload = {
                "customer_id": customer_id,
                "employee_id": emp["id"],
                "scheduled_at": scheduled_iso,
                "notes": "Live testing visit for GPS Check-in and Check-out at current location."
            }
            v_resp = session.post(f"{PROD_API_URL}/api/v1/visits", json=v_payload)
            print(f"Scheduled Visit for {emp.get('full_name')} ({emp.get('employee_code')}): Status {v_resp.status_code}")
else:
    print(f"Login failed: {login_resp.text}")
