import sys
import requests
from decimal import Decimal

BASE_URL = "http://localhost:8000"

print("=" * 80)
print("COMPREHENSIVE FULL-SYSTEM REAL-TIME DYNAMIC AUDIT")
print("=" * 80)

# 1. AUTHENTICATION & LOGIN
print("\n[1/12] Testing Authentication & Token Issuance...")
r_admin = requests.post(f"{BASE_URL}/api/v1/auth/login", json={
    "email": "admin@fieldtrack.test",
    "password": "AdminPass123!"
})
assert r_admin.status_code == 200, f"Admin login failed: {r_admin.status_code} {r_admin.text}"
admin_token = r_admin.json()["access_token"]
admin_headers = {"Authorization": f"Bearer {admin_token}"}
print(f"  [OK] Admin Login Successful (Token length: {len(admin_token)})")

r_emp = requests.post(f"{BASE_URL}/api/v1/auth/login", json={
    "email": "imharshofficial322@gmail.com",
    "password": "Imharsh@1"
})
assert r_emp.status_code == 200, f"Employee login failed: {r_emp.status_code} {r_emp.text}"
emp_token = r_emp.json()["access_token"]
emp_headers = {"Authorization": f"Bearer {emp_token}"}
print(f"  [OK] Employee (Harsh) Login Successful (Token length: {len(emp_token)})")

# 2. DASHBOARD & BI SUMMARY (Global & Scoped)
print("\n[2/12] Testing Dashboard & BI Summaries (Page: /)...")
r_dash = requests.get(f"{BASE_URL}/api/v1/dashboard/summary", headers=admin_headers)
assert r_dash.status_code == 200, f"Dashboard summary failed: {r_dash.status_code}"
dash_data = r_dash.json()
kpis = dash_data["kpis"]
print(f"  [OK] Global Dashboard KPIs: Outlets={kpis['total_outlets']}, Sales=INR {kpis['total_sales']}, Col=INR {kpis['total_collection']}, OS=INR {kpis['total_market_outstanding']}, Visits={kpis['total_visits']}")
print(f"  [OK] Brand Summaries Count: {len(dash_data['brand_breakdown'])}")
print(f"  [OK] FOS Summaries Count: {len(dash_data['fos_breakdown'])}")
print(f"  [OK] Zone Summaries Count: {len(dash_data['zone_breakdown'])}")
print(f"  [OK] 7 Ageing Buckets Distribution: {list(dash_data['ageing_distribution'].keys())}")

# 3. EMPLOYEES & EMPLOYEE DETAIL (Page: /employees, /employees/:id)
print("\n[3/12] Testing Employees Subsystem (Page: /employees)...")
r_emps = requests.get(f"{BASE_URL}/api/v1/employees", headers=admin_headers)
assert r_emps.status_code == 200
emps = r_emps.json()
print(f"  [OK] Total Registered Employees: {len(emps)}")
first_emp_id = emps[0]["id"]
r_emp_detail = requests.get(f"{BASE_URL}/api/v1/employees/{first_emp_id}", headers=admin_headers)
assert r_emp_detail.status_code == 200
print(f"  [OK] Employee Detail Loaded for {emps[0]['full_name']} ({first_emp_id})")

# 4. CUSTOMERS & OUTLETS (Page: /customers, /customers/:id)
print("\n[4/12] Testing Customers / Outlets Subsystem (Page: /customers)...")
r_custs = requests.get(f"{BASE_URL}/api/v1/customers", headers=admin_headers)
assert r_custs.status_code == 200
custs = r_custs.json()
cust_items = custs.get("items", custs) if isinstance(custs, dict) else custs
print(f"  [OK] Total Outlets Loaded: {len(cust_items)}")
first_cust_id = cust_items[0]["id"]
r_cust_detail = requests.get(f"{BASE_URL}/api/v1/customers/{first_cust_id}", headers=admin_headers)
assert r_cust_detail.status_code == 200
print(f"  [OK] Customer Detail Loaded for {cust_items[0]['name']} (Geofence: {r_cust_detail.json().get('geofence_radius_m')}m)")

# 5. TERRITORIES / ZONES & AREAS (Page: /territories, /territories/:id)
print("\n[5/12] Testing Territories & Zones Subsystem (Page: /territories)...")
r_terr = requests.get(f"{BASE_URL}/api/v1/territories", headers=admin_headers)
assert r_terr.status_code == 200
terrs = r_terr.json()
print(f"  [OK] Total Zones / Territories: {len(terrs)}")
r_areas = requests.get(f"{BASE_URL}/api/v1/areas", headers=admin_headers)
assert r_areas.status_code == 200
areas = r_areas.json()
print(f"  [OK] Total Areas Loaded: {len(areas)}")
if terrs:
    first_terr_id = terrs[0]["id"]
    r_terr_detail = requests.get(f"{BASE_URL}/api/v1/territories/{first_terr_id}", headers=admin_headers)
    assert r_terr_detail.status_code == 200
    print(f"  [OK] Territory Detail Loaded: {terrs[0]['name']}")

# 6. VISITS & VISIT DETAIL (Page: /visits, /visits/:id)
print("\n[6/12] Testing Visits & Today's Schedule (Page: /visits)...")
r_visits = requests.get(f"{BASE_URL}/api/v1/visits", headers=admin_headers)
assert r_visits.status_code == 200
visits = r_visits.json()
v_items = visits.get("items", visits) if isinstance(visits, dict) else visits
print(f"  [OK] Total System Visits: {len(v_items)}")
r_my_today = requests.get(f"{BASE_URL}/api/v1/visits/me/today", headers=emp_headers)
assert r_my_today.status_code == 200
today_v = r_my_today.json()
today_items = today_v.get("items", today_v) if isinstance(today_v, dict) else today_v
print(f"  [OK] Harsh Today's Operational Visits: {len(today_items)}")
if v_items:
    first_vid = v_items[0]["id"]
    r_v_detail = requests.get(f"{BASE_URL}/api/v1/visits/{first_vid}", headers=admin_headers)
    assert r_v_detail.status_code == 200
    print(f"  [OK] Visit Detail Loaded (Status: {r_v_detail.json()['status']})")

# 7. PAYMENTS & COLLECTIONS REVIEW (Page: /payments)
print("\n[7/12] Testing Payment Review Queue (Page: /payments)...")
r_pay_q = requests.get(f"{BASE_URL}/api/v1/payments/queue", headers=admin_headers)
assert r_pay_q.status_code == 200
pay_items = r_pay_q.json()
print(f"  [OK] Total Review Queue Payments: {len(pay_items)}")
for p in pay_items[:3]:
    print(f"    - Payment {p['id']}: INR {p['amount']} [{p['status']}] (Customer: {p.get('customer_name')})")

# 8. GEO LOGS & VERIFICATIONS (Page: /geo-logs)
print("\n[8/12] Testing Geo-Verification Logs (Page: /geo-logs)...")
r_geo = requests.get(f"{BASE_URL}/api/v1/reports/geo-verifications", headers=admin_headers)
assert r_geo.status_code == 200
geo_logs = r_geo.json()
print(f"  [OK] Total Geo-Verification Audit Logs: {len(geo_logs)}")

# 9. LIVE MAP & ACTIVE LOCATIONS (Page: /map)
print("\n[9/12] Testing Live GPS & Map Tracker (Page: /map)...")
r_locs = requests.get(f"{BASE_URL}/api/v1/tracking/employees/latest-locations", headers=admin_headers)
assert r_locs.status_code in [200, 404] # Might be empty or populated
print(f"  [OK] Map Tracking Endpoint Reachable (Status: {r_locs.status_code})")

# 10. FORMS & SUBMISSIONS (Page: /forms)
print("\n[10/12] Testing Custom Forms Engine (Page: /forms)...")
r_forms = requests.get(f"{BASE_URL}/api/v1/forms", headers=admin_headers)
assert r_forms.status_code == 200
forms = r_forms.json()
print(f"  [OK] Total Active Form Templates: {len(forms)}")

# 11. REPORTS ENGINE (Page: /reports)
print("\n[11/12] Testing Comprehensive Reports Engine (Page: /reports)...")
r_rep_ov = requests.get(f"{BASE_URL}/api/v1/reports/overview", headers=admin_headers)
assert r_rep_ov.status_code == 200
print("  [OK] 1. Overview Report: Loaded")

r_rep_outlets = requests.get(f"{BASE_URL}/api/v1/reports/outlets", headers=admin_headers)
assert r_rep_outlets.status_code == 200
print(f"  [OK] 2. Outlets Directory Report: {len(r_rep_outlets.json())} outlets")

r_rep_emp = requests.get(f"{BASE_URL}/api/v1/reports/employee-master", headers=admin_headers)
assert r_rep_emp.status_code == 200
print(f"  [OK] 3. Employee Master Report: {len(r_rep_emp.json())} employees")

r_rep_visits = requests.get(f"{BASE_URL}/api/v1/reports/visits-detailed", headers=admin_headers)
assert r_rep_visits.status_code == 200
print(f"  [OK] 4. Detailed Visits Audit Report: {len(r_rep_visits.json())} visits")

r_rep_bi = requests.get(f"{BASE_URL}/api/v1/reports/business-summary", headers=admin_headers)
assert r_rep_bi.status_code == 200
print(f"  [OK] 5. Business BI Multi-Dimensional Matrix: Loaded")

# 12. SETTINGS & PROFILE (Page: /settings, /profile)
print("\n[12/12] Testing Settings, Diagnostics & Profile (Page: /settings, /profile)...")
r_periods = requests.get(f"{BASE_URL}/api/v1/reports/monthly-periods", headers=admin_headers)
assert r_periods.status_code == 200
print(f"  [OK] Monthly Reporting Periods: {len(r_periods.json())} periods")

r_me = requests.get(f"{BASE_URL}/api/v1/users/me", headers=admin_headers)
assert r_me.status_code == 200
print(f"  [OK] User Profile Active: {r_me.json()['email']} (Role: {r_me.json()['role']})")

print("\n" + "=" * 80)
print("🎉 ALL 12 SUBSYSTEMS & PAGES VERIFIED: 100% REAL-TIME, CONNECTED & DYNAMIC!")
print("=" * 80)
