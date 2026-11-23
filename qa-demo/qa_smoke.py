"""
External smoke test for the QA/DEMO environment. Uses only the public HTTPS address + the QA admin login.

    python qa_smoke.py https://<qa-host> <admin-email> <admin-password> [--expect-demo]

Checks: public HTTPS, security headers, login, every major module returns data, key records link together
(outlet -> invoices / payments / visits / requirements / orders), exports work, reconciliation is clean,
API docs are not exposed, no production host appears in any API response, and prints a verdict.
Exit code 0 only if every check passes.
"""
from __future__ import annotations

import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1].rstrip("/")
EMAIL, PASSWORD = sys.argv[2], sys.argv[3]
FORBIDDEN = ("51-79-158-138", "sslip.io", "fieldtrack-pro-rosy", "sgrgservices", "tallyprimecloud", "SGRG SERVICES")
results: list[tuple[bool, str]] = []
bodies: list[str] = []


def call(method, path, token=None, body=None, raw=False, timeout=120):
    req = urllib.request.Request(BASE + path, method=method, data=(json.dumps(body).encode() if body is not None else None))
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
            data = r.read()
            return r.status, dict(r.headers), (data if raw else json.loads(data.decode() or "null"))
    except urllib.error.HTTPError as e:
        data = e.read()
        try:
            return e.code, dict(e.headers), json.loads(data.decode() or "null")
        except Exception:  # noqa: BLE001
            return e.code, dict(e.headers), data[:200]


def check(ok, label, detail=""):
    results.append((bool(ok), label))
    print(("PASS " if ok else "FAIL ") + label + (f"  [{detail}]" if detail else ""))


def n(x):
    if isinstance(x, list):
        return len(x)
    if isinstance(x, dict):
        for k in ("items", "data", "results", "rows"):
            if isinstance(x.get(k), list):
                return len(x[k])
        return len(x)
    return 0


def main():
    t0 = time.time()
    st, h, _ = call("GET", "/health", raw=True)
    check(st == 200 and BASE.startswith("https://"), "public HTTPS /health", f"{st} in {time.time() - t0:.1f}s")
    st, h, page = call("GET", "/", raw=True)
    hl = {k.lower(): v for k, v in h.items()}
    check(st == 200 and b"<div id=\"root\"" in page, "web app served at /")
    check("strict-transport-security" in hl and "content-security-policy" in hl and hl.get("x-content-type-options") == "nosniff", "security headers on the web app")
    for p in ("/docs", "/redoc", "/openapi.json"):
        st, h, body = call("GET", p, raw=True)
        check(b"swagger" not in body.lower() and b"openapi" not in body[:200].lower(), f"API docs not exposed at {p}")
    st, _, tok = call("POST", "/api/v1/auth/login", body={"email": EMAIL, "password": PASSWORD})
    check(st == 200 and "access_token" in tok, "admin login", str(st))
    if st != 200:
        return finish()
    t = tok["access_token"]
    st, _, bad = call("POST", "/api/v1/auth/login", body={"email": EMAIL, "password": "definitely-wrong-password"})
    check(st in (401, 403, 422, 429), "wrong password is rejected", str(st))
    st, _, me = call("GET", "/api/v1/auth/me", t)
    check(st == 200 and me.get("role") == "ADMIN", "profile: role ADMIN", str(me.get("role")))
    st, _, org = call("GET", "/api/v1/organization", t)
    check(st == 200 and "DEMO" in json.dumps(org) and "sgrg" not in json.dumps(org).lower(), "organisation profile is the fictional one")

    def get(path, label, minimum=None, key=None):
        st, h, d = call("GET", path, t)
        bodies.append(json.dumps(d, default=str)[:20000])
        total = h.get("X-Total-Count") or h.get("x-total-count")
        cnt = int(total) if total and str(total).isdigit() else n(d if key is None else d.get(key))
        ok = st == 200 and (minimum is None or cnt >= minimum)
        check(ok, label, f"{st}, {cnt} rows" if minimum is not None else str(st))
        return d

    cust = get("/api/v1/customers?limit=100", "customers (outlets)", 36)
    get("/api/v1/employees?limit=100", "employees (FOS)", 6)
    get("/api/v1/territories", "territories", 2)
    get("/api/v1/areas", "areas", 6)
    get("/api/v1/brands", "brands", 4)
    get("/api/v1/visits?limit=50", "visits", 50)
    get("/api/v1/visits/adhoc-review", "ad-hoc visit review")
    get("/api/v1/payments/queue?status=PENDING_VERIFICATION", "collections awaiting verification", 5)
    get("/api/v1/payments/queue?status=VERIFIED", "verified collections", 5)
    get("/api/v1/collections/overview", "collections overview")
    get("/api/v1/dashboard/summary", "dashboard summary")
    get("/api/v1/dashboard/history-periods", "dashboard history periods")
    get("/api/v1/workday/overview/today", "work-day overview")
    get("/api/v1/requirements", "customer requirements", 8)
    get("/api/v1/orders", "orders", 2)
    get("/api/v1/customers/prospects", "new-outlet requests", 2)
    get("/api/v1/location-proposals", "location corrections", 1)
    get("/api/v1/field-exceptions", "field exceptions", 1)
    get("/api/v1/customers/outlet-proofs?status=ALL", "outlet photographs (proofs)", 4)
    get("/api/v1/notifications/me", "notifications")
    get("/api/v1/form-templates", "form templates", 1)
    get("/api/v1/visit-planning/monthly-plans" if False else "/api/v1/reports/monthly-periods", "monthly reporting periods", 3)
    for rep in ("overview", "employees", "outlets", "outstanding", "collections", "visits-detailed", "employees-master"):
        get(f"/api/v1/reports/{rep}", f"report: {rep}")
    for exp in ("outstanding", "collections", "outlets"):
        st, h, body = call("GET", f"/api/v1/reports/{exp}/export", t, raw=True)
        check(st == 200 and len(body) > 200, f"report export: {exp}", f"{st}, {len(body)} bytes")
    rec = get("/api/v1/integrations/tally/reconciliation", "Tally reconciliation report")
    if isinstance(rec, dict):
        check(rec.get("debtors_with_difference") == 0 and rec.get("debtors_reconciled", 0) >= 30, "reconciliation: every debtor ledger reconciles",
              f"{rec.get('debtors_reconciled')} reconciled, {rec.get('debtors_with_difference')} differences")
    get("/api/v1/integrations/tally/status", "Tally integration status (synthetic agent)")

    # ---- one outlet end to end
    items = cust if isinstance(cust, list) else cust.get("items", [])
    target = next((c for c in items if c.get("outlet_code") == "DEMO-0001"), items[0] if items else None)
    if target:
        cid = target["id"]
        st, _, acc = call("GET", f"/api/v1/customers/{cid}/account", t)
        check(st == 200, f"outlet account / outstanding ({target.get('name')})", str(st))
        for sub, lab in (("invoices", "invoices"), ("history", "visit & payment history"), ("orders", "orders"), ("requirements", "requirements"), ("outlet-proofs", "outlet photographs")):
            st, _, d = call("GET", f"/api/v1/customers/{cid}/{sub}", t)
            check(st == 200, f"outlet -> {lab}", f"{st}, {n(d)} rows")
    # ---- persistence across logout / login
    st, _, tok2 = call("POST", "/api/v1/auth/login", body={"email": EMAIL, "password": PASSWORD})
    st2, _, cust2 = call("GET", "/api/v1/customers?limit=100", tok2.get("access_token") if isinstance(tok2, dict) else None)
    check(st == 200 and st2 == 200 and n(cust2) == n(cust), "data persists across a new login", f"{n(cust2)} outlets")
    # ---- isolation: no production / real-company marker in anything returned
    blob = " ".join(bodies)
    hits = [f for f in FORBIDDEN if f.lower() in blob.lower()]
    check(not hits, "no production host or real-company marker in any API response", ", ".join(hits))
    finish()


def finish():
    bad = [l for ok, l in results if not ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} checks passed" + (f"; FAILED: {bad}" if bad else ""))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
