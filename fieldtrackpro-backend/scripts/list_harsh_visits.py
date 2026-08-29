import requests

LOCAL_API_URL = "http://localhost:8000"

resp = requests.post(f"{LOCAL_API_URL}/api/v1/auth/login", json={
    "email": "imharshofficial322@gmail.com",
    "password": "Imharsh@1"
}, timeout=10).json()

token = resp["access_token"]
visits = requests.get(f"{LOCAL_API_URL}/api/v1/visits/me/today", headers={"Authorization": f"Bearer {token}"}, timeout=10).json()
items = visits.get("items", []) if isinstance(visits, dict) else visits

print(f"Total visits on local backend for Harsh: {len(items)}")
for v in items:
    print(f"- ID: {v.get('id')} | Status: {v.get('status')} | Outlet: {v.get('customer_name')}")
