import requests
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
PROD_API_URL = "https://fieldtrackpro-backend-s7hs.onrender.com"

# Target Coordinates (Current Device GPS Location)
LAT = 26.734115
LON = 80.943602
GEOFENCE_RADIUS = 500 # 500 meters

session = requests.Session()

# 1. Admin login
r_login = session.post(f"{PROD_API_URL}/api/v1/auth/login", json={
    "email": "admin@fieldtrack.test",
    "password": "AdminPass123!"
}, timeout=30)
token = r_login.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
session.headers.update(headers)

# 2. Create customer with exact GPS coordinates
create_cust_payload = {
    "name": "Harsh Home / Current Location",
    "contact_number": "9565249244",
    "contact_person": "Harsh Vardhan Tripathi",
    "address": "Telibagh, Lucknow (Current GPS Location)",
    "latitude": LAT,
    "longitude": LON,
    "geofence_radius_m": GEOFENCE_RADIUS,
    "location_status": "VERIFIED",
    "outlet_code": "HARSH-LOC-01"
}

r_cust = session.post(f"{PROD_API_URL}/api/v1/customers", json=create_cust_payload, timeout=30)
print(f"Create customer response: {r_cust.status_code} -> {r_cust.text}")
if r_cust.status_code in [200, 201]:
    customer_id = r_cust.json()["id"]
else:
    # Search for it
    r_search = session.get(f"{PROD_API_URL}/api/v1/customers?search=Harsh%20Home", timeout=30)
    customer_id = r_search.json()[0]["id"]
    # Update lat/lon
    session.put(f"{PROD_API_URL}/api/v1/customers/{customer_id}", json={
        "latitude": LAT,
        "longitude": LON,
        "geofence_radius_m": GEOFENCE_RADIUS
    }, timeout=30)

print(f"Customer ID: {customer_id} at ({LAT}, {LON})")

# 3. Find Harsh Employee ID
emps = session.get(f"{PROD_API_URL}/api/v1/employees?search=Harsh", timeout=30).json()
harsh_emp_id = emps[0]["id"]
print(f"Harsh employee ID: {harsh_emp_id}")

# 4. Schedule visit for 30th August 2026
scheduled_iso = datetime(2026, 8, 30, 10, 0, 0, tzinfo=IST).isoformat()
visit_payload = {
    "customer_id": customer_id,
    "employee_id": harsh_emp_id,
    "scheduled_at": scheduled_iso,
    "notes": "Testing check-in and checkout at current location."
}
r_v = session.post(f"{PROD_API_URL}/api/v1/visits", json=visit_payload, timeout=30)
print(f"Scheduled Visit for Harsh: {r_v.status_code} -> {r_v.text}")

# 5. Also delete or reassign the old Kanpur visit if any
# Login as Harsh and check visits
r_hlogin = requests.post(f"{PROD_API_URL}/api/v1/auth/login", json={
    "email": "imharshofficial322@gmail.com",
    "password": "Imharsh@1"
}, timeout=30)
h_token = r_hlogin.json()["access_token"]
h_headers = {"Authorization": f"Bearer {h_token}"}
r_hvisits = requests.get(f"{PROD_API_URL}/api/v1/visits", headers=h_headers, timeout=30).json()
visits_list = r_hvisits.get("items", []) if isinstance(r_hvisits, dict) else r_hvisits

print("\n--- Current Scheduled Visits for Harsh on August 30th ---")
for v in visits_list:
    print(f"Visit ID: {v.get('id')}")
    print(f"  Outlet: {v.get('customer_name')}")
    print(f"  Address: {v.get('customer_address')}")
    print(f"  Scheduled: {v.get('scheduled_at')}")
    print(f"  Status: {v.get('status')}")
