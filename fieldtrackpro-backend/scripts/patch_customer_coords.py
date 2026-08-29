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

# 2. Patch customer coordinates with correct nested structure
customer_id = "e712f563-4875-4a94-b8d1-bc2a5cc2159a"
patch_payload = {
    "name": "Harsh Home / Current Location",
    "address": "Telibagh, Lucknow (Current GPS Location)",
    "location": {
        "latitude": LAT,
        "longitude": LON
    },
    "geofence_radius_m": GEOFENCE_RADIUS,
    "location_status": "VERIFIED"
}

r_patch = session.patch(f"{PROD_API_URL}/api/v1/customers/{customer_id}", json=patch_payload, timeout=30)
print(f"Customer patch status: {r_patch.status_code} -> {r_patch.text[:200]}")

# 3. Verify by logging in as imharshofficial322@gmail.com
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
    print("VERIFIED HARSH TODAY'S VISITS (/api/v1/visits/me/today):")
    print("="*60)
    for v in today_visits:
        print(f"Visit ID : {v.get('id')}")
        print(f"Outlet   : {v.get('customer_name')}")
        print(f"Address  : {v.get('customer_address')}")
        print(f"Coords   : Lat {v.get('customer_latitude')}, Lon {v.get('customer_longitude')}")
        print(f"Geofence : {v.get('customer_geofence_radius_m')}m")
        print(f"Scheduled: {v.get('scheduled_at')}")
        print(f"Status   : {v.get('status')}")
