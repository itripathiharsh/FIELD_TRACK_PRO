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

# 2. Get customer ID for Harsh Home / Current Location (e712f563-4875-4a94-b8d1-bc2a5cc2159a)
customer_id = "e712f563-4875-4a94-b8d1-bc2a5cc2159a"

# Ensure customer coordinates and radius are exact
r_c_upd = session.put(f"{PROD_API_URL}/api/v1/customers/{customer_id}", json={
    "name": "Harsh Home / Current Location",
    "address": "Telibagh, Lucknow (Current GPS Location)",
    "latitude": LAT,
    "longitude": LON,
    "geofence_radius_m": GEOFENCE_RADIUS,
    "location_status": "VERIFIED"
}, timeout=30)
print(f"Customer update status: {r_c_upd.status_code}")

# 3. Find Harsh Employee ID (ac2abf41-e62c-4147-a42b-e507232aac38)
harsh_emp_id = "ac2abf41-e62c-4147-a42b-e507232aac38"

# 4. Mark old visit e845d9c7-bb83-40ed-88f0-2dd2a1bf72ef as MISSED
r_cancel = session.patch(
    f"{PROD_API_URL}/api/v1/visits/e845d9c7-bb83-40ed-88f0-2dd2a1bf72ef/status",
    json={"status": "MISSED", "reason": "Replaced with current location test"},
    timeout=30
)
print(f"Old visit override to MISSED: {r_cancel.status_code} -> {r_cancel.text[:100]}")

# Schedule new visit at Harsh Home / Current Location
scheduled_iso = datetime(2026, 8, 30, 10, 0, 0, tzinfo=IST).isoformat()
visit_payload = {
    "customer_id": customer_id,
    "employee_id": harsh_emp_id,
    "scheduled_at": scheduled_iso,
    "notes": "Testing GPS checkin and checkout at current location."
}
r_v = session.post(f"{PROD_API_URL}/api/v1/visits", json=visit_payload, timeout=30)
print(f"Scheduled new visit: {r_v.status_code} -> {r_v.text}")

# 5. Verify by logging in as imharshofficial322@gmail.com
r_hlogin = requests.post(f"{PROD_API_URL}/api/v1/auth/login", json={
    "email": "imharshofficial322@gmail.com",
    "password": "Imharsh@1"
}, timeout=30)

if r_hlogin.status_code == 200:
    h_token = r_hlogin.json()["access_token"]
    h_headers = {"Authorization": f"Bearer {h_token}"}
    r_hvisits = requests.get(f"{PROD_API_URL}/api/v1/visits/me/today", headers=h_headers, timeout=30).json()
    today_visits = r_hvisits.get("items", []) if isinstance(r_hvisits, dict) else r_hvisits

    print("\n" + "="*60)
    print("HARSH TODAY'S VISITS (/api/v1/visits/me/today):")
    print("="*60)
    for v in today_visits:
        print(f"Visit ID : {v.get('id')}")
        print(f"Outlet   : {v.get('customer_name')}")
        print(f"Address  : {v.get('customer_address')}")
        print(f"Coords   : Lat {v.get('customer_latitude')}, Lon {v.get('customer_longitude')}")
        print(f"Geofence : {v.get('customer_geofence_radius_m')}m")
        print(f"Scheduled: {v.get('scheduled_at')}")
        print(f"Status   : {v.get('status')}")
