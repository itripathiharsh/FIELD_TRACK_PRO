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

# 2. Get customer ID for Harsh Home
r_search = session.get(f"{PROD_API_URL}/api/v1/customers?search=Harsh%20Home", timeout=30)
cust_data = r_search.json()
customer_id = cust_data[0]["id"]
print(f"Harsh Customer ID: {customer_id}")

# 3. Find Harsh Employee ID (ac2abf41-e62c-4147-a42b-e507232aac38 or find by search)
emps = session.get(f"{PROD_API_URL}/api/v1/employees?limit=200", timeout=30).json()
harsh_emps = [e for e in (emps.get("items", []) if isinstance(emps, dict) else emps) if "Harsh" in e.get("full_name", "")]
print(f"Found Harsh employees: {[(e.get('id'), e.get('full_name'), e.get('employee_code')) for e in harsh_emps]}")

# 4. For each harsh employee profile, delete/cancel old visits and assign to Harsh Home
scheduled_iso = datetime(2026, 8, 30, 11, 0, 0, tzinfo=IST).isoformat()

for emp in harsh_emps:
    emp_id = emp["id"]
    # Check visits
    r_vlist = session.get(f"{PROD_API_URL}/api/v1/visits?employee_id={emp_id}", timeout=30).json()
    vlist = r_vlist.get("items", []) if isinstance(r_vlist, dict) else r_vlist
    for v in vlist:
        v_id = v.get("id")
        # Cancel / delete
        r_del = session.delete(f"{PROD_API_URL}/api/v1/visits/{v_id}", timeout=30)
        print(f"Deleted old visit {v_id} for {emp.get('full_name')}: {r_del.status_code}")
    
    # Now schedule the new visit at Harsh Home / Current Location
    visit_payload = {
        "customer_id": customer_id,
        "employee_id": emp_id,
        "scheduled_at": scheduled_iso,
        "notes": "Testing GPS checkin and checkout at current location."
    }
    r_v = session.post(f"{PROD_API_URL}/api/v1/visits", json=visit_payload, timeout=30)
    print(f"Scheduled new visit for {emp.get('full_name')} ({emp.get('employee_code')}): {r_v.status_code} -> {r_v.text}")

# 5. Verify by logging in as imharshofficial322@gmail.com
r_hlogin = requests.post(f"{PROD_API_URL}/api/v1/auth/login", json={
    "email": "imharshofficial322@gmail.com",
    "password": "Imharsh@1"
}, timeout=30)

if r_hlogin.status_code == 200:
    h_token = r_hlogin.json()["access_token"]
    h_headers = {"Authorization": f"Bearer {h_token}"}
    r_hvisits = requests.get(f"{PROD_API_URL}/api/v1/visits", headers=h_headers, timeout=30).json()
    visits_list = r_hvisits.get("items", []) if isinstance(r_hvisits, dict) else r_hvisits

    print("\n========================================================")
    print("FINAL VERIFICATION FOR imharshofficial322@gmail.com:")
    print("========================================================")
    for v in visits_list:
        print(f"✅ Visit ID : {v.get('id')}")
        print(f"   Outlet   : {v.get('customer_name')}")
        print(f"   Address  : {v.get('customer_address')}")
        print(f"   Date     : {v.get('scheduled_at')}")
        print(f"   Status   : {v.get('status')}")
