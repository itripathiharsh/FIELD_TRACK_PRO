import requests
from datetime import datetime, timezone, timedelta
import asyncio

PROD_API_URL = "https://fieldtrackpro-backend-s7hs.onrender.com"
LOCAL_API_URL = "http://localhost:8000"

LAT = 26.734115
LON = 80.943602
GEOFENCE_RADIUS = 500
IST = timezone(timedelta(hours=5, minutes=30))

print("="*60)
print("CREATING TEST VISIT #2 ON PRODUCTION RENDER")
print("="*60)

try:
    r_admin = requests.post(f"{PROD_API_URL}/api/v1/auth/login", json={
        "email": "admin@fieldtrack.test",
        "password": "AdminPass123!"
    }, timeout=90)
    if r_admin.status_code != 200:
        print(f"Prod admin login failed: {r_admin.status_code}")
        exit(1)
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
        # Update coordinates
        requests.patch(f"{PROD_API_URL}/api/v1/customers/{customer_id}", json={
            "location": {"latitude": LAT, "longitude": LON},
            "geofence_radius_m": GEOFENCE_RADIUS,
            "location_status": "VERIFIED"
        }, headers=headers, timeout=30)
        print(f"Using/Updated Prod Customer: {customer_id}")

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

    # 4. Verify by querying Harsh's visits on both Local and Prod
    print("\n--- Verifying Visits for Harsh ---")
    for name, base_url in [("LOCAL (http://localhost:8000)", LOCAL_API_URL), ("PROD (Render)", PROD_API_URL)]:
        try:
            r_hl = requests.post(f"{base_url}/api/v1/auth/login", json={
                "email": "imharshofficial322@gmail.com",
                "password": "Imharsh@1"
            }, timeout=10)
            if r_hl.status_code == 200:
                h_tok = r_hl.json()["access_token"]
                h_h = {"Authorization": f"Bearer {h_tok}"}
                r_vlist = requests.get(f"{base_url}/api/v1/visits/me/today", headers=h_h, timeout=10).json()
                vitems = r_vlist.get("items", []) if isinstance(r_vlist, dict) else r_vlist
                print(f"{name}: Found {len(vitems)} today's visits:")
                for v in vitems:
                    print(f"  - [{v.get('status')}] {v.get('customer_name')} (ID: {v.get('id')})")
        except Exception as err:
            print(f"Check {name} error: {err}")

except Exception as e:
    print(f"Error: {e}")
