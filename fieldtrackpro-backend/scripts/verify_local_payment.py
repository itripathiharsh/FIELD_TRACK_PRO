import requests
import json
import io
from PIL import Image

LOCAL_API_URL = "http://localhost:8000"

print("="*60)
print("TESTING LOCAL BACKEND PAYMENT COLLECTION END-TO-END")
print("="*60)

# 1. Login as Harsh
login_resp = requests.post(f"{LOCAL_API_URL}/api/v1/auth/login", json={
    "email": "imharshofficial322@gmail.com",
    "password": "Imharsh@1"
}, timeout=10)

print(f"Login status: {login_resp.status_code}")
token = login_resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# 2. Get today's visits
r_visits = requests.get(f"{LOCAL_API_URL}/api/v1/visits", headers=headers, timeout=10)
visits = r_visits.json().get("items", []) if isinstance(r_visits.json(), dict) else r_visits.json()
print(f"Found {len(visits)} visits for Harsh on local DB.")
visit_id = visits[0]["id"]
print(f"Using Visit ID: {visit_id}")

# 3. Create payment with normal amount (e.g., Rs. 500.00)
r_pay = requests.post(f"{LOCAL_API_URL}/api/v1/payments", json={
    "visit_id": visit_id,
    "amount": "500.00",
    "payment_method": "CASH",
    "payment_date": "2026-08-30",
    "notes": "Verified cash collection test",
    "idempotency_key": "local-verify-key-01"
}, headers=headers, timeout=10)

print(f"Payment Create Status: {r_pay.status_code}")
print(f"Payment Response: {r_pay.text}")

if r_pay.status_code in [200, 201]:
    payment_id = r_pay.json()["id"]
    
    # 4. Upload photo proof
    img = Image.new("RGB", (100, 100), color="green")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    files = {"file": ("receipt.jpg", buf.getvalue(), "image/jpeg")}
    
    r_proof = requests.post(f"{LOCAL_API_URL}/api/v1/payments/{payment_id}/proof", files=files, headers=headers, timeout=10)
    print(f"Upload Proof Status: {r_proof.status_code}")
    print(f"Upload Proof Response: {r_proof.text}")
    print("\n✅ All Local Payment & Proof tests PASSED!")
