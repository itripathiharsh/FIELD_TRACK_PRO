import requests

print("="*60)
print("TESTING PRODUCTION RENDER API")
print("="*60)

r = requests.get("https://fieldtrackpro-backend-s7hs.onrender.com/health", timeout=20)
print("Production Render Health:", r.status_code, r.json())

r_login = requests.post("https://fieldtrackpro-backend-s7hs.onrender.com/api/v1/auth/login", json={
    "email": "imharshofficial322@gmail.com",
    "password": "Imharsh@1"
}, timeout=20)
print("Harsh Production Login:", r_login.status_code)

token = r_login.json()["access_token"]
r_v = requests.get("https://fieldtrackpro-backend-s7hs.onrender.com/api/v1/visits/me/today", headers={
    "Authorization": f"Bearer {token}"
}, timeout=20)

items = r_v.json().get("items", []) if isinstance(r_v.json(), dict) else r_v.json()
print(f"Harsh Production Today Visits Count: {len(items)}")
for v in items:
    print(f"  - [{v.get('status')}] {v.get('customer_name')} (ID: {v.get('id')})")
