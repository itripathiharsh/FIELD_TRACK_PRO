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

if login_resp.status_code != 200:
    print(f"Admin login failed: {login_resp.status_code} - {login_resp.text}")
    exit(1)

token = login_resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
session.headers.update(headers)
print("Admin logged in successfully.")

# 2. Check if Harsh already exists or register Harsh
harsh_email = "imharshofficial322@gmail.com"
harsh_pass = "Imharsh@1"
harsh_phone = "9565249244"

# Try registering Harsh as an Employee with Role.EMPLOYEE (or ADMIN)
register_payload = {
    "user": {
        "email": harsh_email,
        "mobile_number": harsh_phone,
        "password": harsh_pass,
        "role": "EMPLOYEE"
    },
    "full_name": "Harsh Tripathi",
    "employee_code": "HARSH01",
    "working_profile": "Lead / Field Executive",
    "cug": harsh_phone
}

r_reg = session.post(f"{PROD_API_URL}/api/v1/employees/register", json=register_payload, timeout=30)
print(f"Register Harsh response: {r_reg.status_code} -> {r_reg.text[:200]}")

# 3. Find Harsh Employee ID
emps_resp = session.get(f"{PROD_API_URL}/api/v1/employees?limit=200", timeout=30)
employees = emps_resp.json().get("items", []) if isinstance(emps_resp.json(), dict) else emps_resp.json()
harsh_emp = None
for e in employees:
    u = e.get("user") or {}
    if u.get("email") == harsh_email or e.get("full_name") == "Harsh Tripathi" or e.get("employee_code") == "HARSH01":
        harsh_emp = e
        break

if not harsh_emp:
    print("Could not find Harsh employee profile!")
else:
    harsh_emp_id = harsh_emp["id"]
    print(f"Found Harsh Employee Profile ID: {harsh_emp_id}")

    # 4. Find or Create Customer
    cust_resp = session.get(f"{PROD_API_URL}/api/v1/customers?limit=100", timeout=30)
    cust_items = cust_resp.json().get("items", []) if isinstance(cust_resp.json(), dict) else cust_resp.json()
    customer_id = None
    for c in cust_items:
        if "Current Location" in c.get("name", "") or "Harsh Live Test" in c.get("name", ""):
            customer_id = c["id"]
            # update customer coords to exact lat/lon
            session.put(f"{PROD_API_URL}/api/v1/customers/{customer_id}", json={
                "name": "Current Location Test Outlet",
                "latitude": LAT,
                "longitude": LON,
                "geofence_radius_m": GEOFENCE_RADIUS,
                "address": "Current GPS Location (Telibagh / Lucknow)",
                "location_status": "VERIFIED"
            })
            print(f"Updated Customer {customer_id} coordinates to ({LAT}, {LON})")
            break
    
    if not customer_id and cust_items:
        customer_id = cust_items[0]["id"]

    # 5. Schedule Visit for Harsh for 30th August 2026
    scheduled_iso = datetime(2026, 8, 30, 10, 0, 0, tzinfo=IST).isoformat()
    visit_payload = {
        "customer_id": customer_id,
        "employee_id": harsh_emp_id,
        "scheduled_at": scheduled_iso,
        "notes": "Live testing visit for GPS Check-in and Check-out at current location."
    }
    v_resp = session.post(f"{PROD_API_URL}/api/v1/visits", json=visit_payload, timeout=30)
    print(f"Scheduled Visit for Harsh: Status {v_resp.status_code} -> {v_resp.text}")

    # 6. Test Login with Harsh's account directly
    r_hlogin = requests.post(f"{PROD_API_URL}/api/v1/auth/login", json={
        "email": harsh_email,
        "password": harsh_pass
    }, timeout=30)
    print(f"Direct login as {harsh_email}: {r_hlogin.status_code}")
    if r_hlogin.status_code == 200:
        h_token = r_hlogin.json()["access_token"]
        h_headers = {"Authorization": f"Bearer {h_token}"}
        # Check visits for Harsh
        r_hvisits = requests.get(f"{PROD_API_URL}/api/v1/visits", headers=h_headers, timeout=30)
        print(f"Harsh's visits API status: {r_hvisits.status_code}")
        h_vlist = r_hvisits.json().get("items", []) if isinstance(r_hvisits.json(), dict) else r_hvisits.json()
        print(f"Harsh has {len(h_vlist)} visits scheduled.")
        for v in h_vlist:
            c = v.get("customer") or {}
            print(f" -> Visit {v.get('id')}: Date={v.get('scheduled_at')}, Status={v.get('status')}, Customer={c.get('name')}")
