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

if login_resp.status_code == 200:
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    session.headers.update(headers)

    # 2. Get Employees
    emps_resp = session.get(f"{PROD_API_URL}/api/v1/employees?limit=100")
    employees = emps_resp.json().get("items", []) if isinstance(emps_resp.json(), dict) else emps_resp.json()

    # 3. Find or create Customer at current GPS location
    cust_resp = session.get(f"{PROD_API_URL}/api/v1/customers?limit=100")
    cust_items = cust_resp.json().get("items", []) if isinstance(cust_resp.json(), dict) else cust_resp.json()
    
    customer_id = None
    for c in cust_items:
        if "Current Location" in c.get("name", "") or "Harsh Live Test" in c.get("name", ""):
            customer_id = c["id"]
            break
    
    if not customer_id and cust_items:
        customer_id = cust_items[0]["id"]

    print(f"Using customer {customer_id}")
    scheduled_iso = datetime(2026, 8, 30, 10, 0, 0, tzinfo=IST).isoformat()
    
    for emp in employees:
        v_payload = {
            "customer_id": customer_id,
            "employee_id": emp["id"],
            "scheduled_at": scheduled_iso,
            "notes": "Live testing visit for GPS Check-in and Check-out at current location."
        }
        v_resp = session.post(f"{PROD_API_URL}/api/v1/visits", json=v_payload)
        print(f"Scheduled for {emp.get('full_name')} ({emp.get('employee_code')}): Status {v_resp.status_code}")
