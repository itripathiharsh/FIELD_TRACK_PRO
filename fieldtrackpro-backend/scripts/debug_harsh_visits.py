import requests
import json

PROD_API_URL = "https://fieldtrackpro-backend-s7hs.onrender.com"
LOCAL_API_URL = "http://localhost:8000"

print("="*60)
print("CHECKING USER & VISITS FOR imharshofficial322@gmail.com")
print("="*60)

for name, base_url in [("LOCAL", LOCAL_API_URL), ("PRODUCTION", PROD_API_URL)]:
    print(f"\n--- Checking {name} ({base_url}) ---")
    try:
        # Try login with Harsh's account
        # Try different passwords
        token = None
        for pwd in ["Imharsh@1", "Password@123!", "AdminPass123!"]:
            r = requests.post(f"{base_url}/api/v1/auth/login", json={
                "email": "imharshofficial322@gmail.com",
                "password": pwd
            }, timeout=10)
            if r.status_code == 200:
                print(f"Login success with password '{pwd}'!")
                token = r.json().get("access_token")
                user_info = r.json().get("user", {})
                print(f"User info: id={user_info.get('id')}, email={user_info.get('email')}, role={user_info.get('role')}")
                break
        
        if not token:
            print("Login with imharshofficial322@gmail.com failed. Checking if user exists via admin...")
            r_admin = requests.post(f"{base_url}/api/v1/auth/login", json={
                "email": "admin@fieldtrack.test",
                "password": "AdminPass123!"
            }, timeout=10)
            if r_admin.status_code == 200:
                admin_token = r_admin.json()["access_token"]
                headers = {"Authorization": f"Bearer {admin_token}"}
                r_users = requests.get(f"{base_url}/api/v1/users", headers=headers, timeout=10)
                print(f"Admin users query: {r_users.status_code}")
                # check employees
                r_emps = requests.get(f"{base_url}/api/v1/employees?limit=100", headers=headers, timeout=10)
                emps = r_emps.json().get("items", []) if isinstance(r_emps.json(), dict) else r_emps.json()
                harsh_emps = [e for e in emps if "harsh" in str(e).lower()]
                print(f"Harsh in employees: {harsh_emps}")
        else:
            headers = {"Authorization": f"Bearer {token}"}
            # Check today's visits / visits endpoint
            r_visits = requests.get(f"{base_url}/api/v1/visits", headers=headers, timeout=10)
            print(f"Visits endpoint: status={r_visits.status_code}")
            if r_visits.status_code == 200:
                v_data = r_visits.json()
                visits = v_data.get("items", []) if isinstance(v_data, dict) else v_data
                print(f"Found {len(visits)} visits for Harsh:")
                for v in visits:
                    cust = v.get("customer", {}) or {}
                    print(f"  - Visit ID: {v.get('id')}, Status: {v.get('status')}, Scheduled: {v.get('scheduled_at')}")
                    print(f"    Customer: {cust.get('name')}, Address: {cust.get('address')}, Lat: {cust.get('latitude')}, Lon: {cust.get('longitude')}")

            # Check dashboard / today's visits endpoint if any
            for ep in ["/api/v1/dashboard", "/api/v1/visits/today", "/api/v1/visits/my"]:
                r_ep = requests.get(f"{base_url}{ep}", headers=headers, timeout=5)
                if r_ep.status_code == 200:
                    print(f"{ep} response: {r_ep.json()}")

    except Exception as e:
        print(f"Error on {name}: {e}")
