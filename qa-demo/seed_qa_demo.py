"""
FieldTrack Pro QA/DEMO dataset - fictional, internally consistent, built into a FRESH database only.

    python seed_qa_demo.py A        # organisation, employees, outlets, Tally-style ledgers / bills / receipts
    python seed_qa_demo.py B        # historical field activity (past 75 days): visits, GPS, collections, requirements
    python seed_qa_demo.py C        # live workflows through the real API: check-ins, photos, approvals, orders
    python seed_qa_demo.py all

Safety: refuses to run unless DATABASE_URL points at the local, empty-or-QA-only database `fieldtrackpro_qa_build`
(never fieldtrackpro_dev, never any remote host). Nothing here contacts Tally, production, or any external service.
Every record is fictional: names, phone numbers, addresses, GSTINs, bill numbers.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import random
import re
import secrets
import string
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = Path(r"F:\Field track pro v2 for test\field track pro\fieldtrackpro-backend")
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(HERE))
import setup_build_db as sb  # noqa: E402

_e = sb.test_env()
if not re.search(r"@(127\.0\.0\.1|localhost):\d+/fieldtrackpro_qa_build$", _e["DATABASE_URL"]):
    sys.exit("STOPPED: DATABASE_URL is not the local fieldtrackpro_qa_build database")
os.environ.update({"DATABASE_URL": _e["DATABASE_URL"], "MIGRATION_DATABASE_URL": _e["MIGRATION_DATABASE_URL"],
                   "ENVIRONMENT": "dev", "ENABLE_SCHEDULER": "false", "TALLY_WRITEBACK_ENABLED": "false",
                   "MEDIA_STORAGE_PATH": str(HERE / "media_storage")})   # QA media stays out of the dev backend folder

import asyncpg  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402

API = "/api/v1"
IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime.now(timezone.utc)
TODAY = datetime.now(IST).date()
RNG = random.Random(20261124)
PRIVATE = HERE / "private"
PRIVATE.mkdir(exist_ok=True)
CRED_FILE = PRIVATE / "qa_credentials.json"
STATE_FILE = PRIVATE / "build_state.json"
CENT = Decimal("0.01")
COMPANY_GUID = "DEMO-QA-COMPANY"
COMPANY_NAME = "DEMO Distribution Co. (fictional - QA only)"

ADMIN_EMAIL = "qa.admin@fieldtrack-demo.test"
TERRITORIES = {
    "DEMO North Zone": [("Lakeview Market", 26.4890, 80.3010), ("Hillside Colony", 26.5010, 80.3180), ("Riverside Road", 26.4760, 80.2890)],
    "DEMO South Zone": [("Station Bazaar", 26.4410, 80.3510), ("Industrial Estate", 26.4290, 80.3690), ("Orchard Lane", 26.4170, 80.3380)],
}
EMPLOYEES = [  # (full name, employee code, mobile) - fictional
    ("Aarav Mehta", "DEMO-FOS-01", "+919999000101"), ("Diya Kapoor", "DEMO-FOS-02", "+919999000102"),
    ("Kabir Sethi", "DEMO-FOS-03", "+919999000103"), ("Meera Nair", "DEMO-FOS-04", "+919999000104"),
    ("Rohan Bhatt", "DEMO-FOS-05", "+919999000105"), ("Tara Joshi", "DEMO-FOS-06", "+919999000106"),
]
PREFIX = ["Sunrise", "Maple", "Cedar", "Lotus", "Falcon", "Ruby", "Coral", "Summit", "Harmony", "Pioneer", "Zephyr", "Nimbus",
          "Aurora", "Beacon", "Crescent", "Delta", "Emerald", "Fortune", "Glacier", "Horizon", "Indigo", "Jasmine"]
SUFFIX = ["Electronics", "Mobile Point", "Telecom", "Appliances", "Gadget House", "Digital Store", "Home Needs", "Communication"]
BRANDS = ["Anchor", "Finolex", "Havells", "USHA", "VU", "Zebronics"]
CONTACTS = ["Anil Verma", "Sunita Rao", "Imran Khan", "Pooja Singh", "Vikram Das", "Neha Gupta", "Rakesh Iyer", "Farah Ali",
            "Manoj Pillai", "Shweta Menon", "Deepak Roy", "Lata Bose"]
DAYS_AGO = [4, 9, 16, 24, 33, 45, 58, 72, 88, 104, 125, 150]
CREDIT_DAYS = 30
SNAP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def q(v) -> Decimal:
    return Decimal(str(v)).quantize(CENT, rounding=ROUND_HALF_UP)


def jpeg(label: str, w=640, h=480, tone=0) -> bytes:
    """A synthetic, clearly-labelled DEMO photo (generated here; no real imagery)."""
    from PIL import Image, ImageDraw
    palette = [(30, 58, 95), (200, 150, 40), (60, 120, 90), (120, 60, 90), (90, 90, 90)]
    bg = palette[tone % len(palette)]
    im = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(im)
    d.rectangle([20, 20, w - 20, h - 20], outline=(255, 255, 255), width=4)
    d.rectangle([w * 0.2, h * 0.45, w * 0.8, h * 0.85], fill=(235, 235, 235))
    d.rectangle([w * 0.2, h * 0.25, w * 0.8, h * 0.4], fill=(245, 190, 60))
    d.text((w * 0.22, h * 0.29), label[:38], fill=(20, 20, 20))
    d.text((24, 26), "DEMO / TEST IMAGE - SYNTHETIC", fill=(255, 255, 255))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=82)
    return b.getvalue()


def load_state() -> dict:
    return json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}


def save_state(st: dict) -> None:
    STATE_FILE.write_text(json.dumps(st, indent=1, default=str), encoding="utf-8")


def creds() -> dict:
    if CRED_FILE.exists():
        return json.loads(CRED_FILE.read_text(encoding="utf-8"))
    alnum = string.ascii_letters + string.digits
    c = {"admin_email": ADMIN_EMAIL,
         "admin_password": "QaDemo-" + "".join(secrets.choice(alnum) for _ in range(9)) + "!7",
         "employee_password": "FosDemo-" + "".join(secrets.choice(alnum) for _ in range(10)) + "!4"}
    CRED_FILE.write_text(json.dumps(c, indent=1), encoding="utf-8")
    return c


class Ctx:
    def __init__(self):
        self.http = AsyncClient(transport=ASGITransport(app=app), base_url="http://qa", timeout=60)
        self.con: asyncpg.Connection | None = None
        self.st = load_state()
        self.cred = creds()
        self.tokens: dict[str, str] = {}

    async def open(self):
        self.con = await asyncpg.connect(_e["MIGRATION_DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://"))

    async def close(self):
        await self.http.aclose()
        if self.con:
            await self.con.close()
        from app.database import engine
        await engine.dispose()
        save_state(self.st)

    async def call(self, method, path, token=None, ok=(200, 201, 204), **kw):
        h = dict(kw.pop("headers", {}))
        if token:
            h["Authorization"] = f"Bearer {token}"
        r = await self.http.request(method, API + path, headers=h, **kw)
        if ok is not None and r.status_code not in ok:
            raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:600]}")
        return r

    async def login(self, email, password):
        r = await self.call("POST", "/auth/login", json={"email": email, "password": password})
        return r.json()["access_token"]


# ===================================================================================== PHASE A
async def phase_a(c: Ctx):
    con = c.con
    if await con.fetchval("select count(*) from users") or await con.fetchval("select count(*) from customers"):
        sys.exit("STOPPED: the build database is not empty - recreate it first (setup_build_db.py create)")
    cr = c.cred
    await con.execute("insert into users (id,email,password_hash,role,is_active,created_at,updated_at) values ($1,$2,$3,'ADMIN',true,now(),now())",
                      uuid.uuid4(), cr["admin_email"], hash_password(cr["admin_password"]))
    ah = c.tokens["admin"] = await c.login(cr["admin_email"], cr["admin_password"])
    print("admin login ok")

    # ---- territories / areas
    areas, terr_ids = [], {}
    for tname, alist in TERRITORIES.items():
        t = (await c.call("POST", "/territories", ah, json={"name": tname, "description": "Fictional demo territory"})).json()
        terr_ids[tname] = t["id"]
        for aname, lat, lng in alist:
            a = (await c.call("POST", "/areas", ah, json={"name": aname, "territory_id": t["id"]})).json()
            areas.append({"id": a["id"], "name": aname, "territory": tname, "territory_id": t["id"], "lat": lat, "lng": lng})
    print("territories", len(terr_ids), "areas", len(areas))

    # ---- employees (one per area)
    emps = []
    for i, (name, code, mobile) in enumerate(EMPLOYEES):
        area = areas[i]
        body = {"user": {"email": f"{name.split()[0].lower()}.fos@fieldtrack-demo.test", "password": cr["employee_password"], "role": "EMPLOYEE",
                         "mobile_number": mobile},
                "full_name": name, "employee_code": code, "territory_id": area["territory_id"], "working_profile": "Field Sales Officer (FOS)"}
        r = await c.call("POST", "/employees/register", ah, json=body)
        e = r.json()
        emps.append({"id": e["id"], "user_id": e.get("user_id") or (e.get("user") or {}).get("id"), "name": name, "code": code,
                     "email": body["user"]["email"], "mobile": mobile, "area": area})
        await c.call("POST", f"/employees/{e['id']}/areas", ah, json={"area_id": area["id"]})
    print("employees", len(emps))

    # ---- outlets (6 per area)
    used, outlets = set(), []
    for ai, area in enumerate(areas):
        for k in range(6):
            while True:
                nm = f"{RNG.choice(PREFIX)} {RNG.choice(SUFFIX)}"
                if nm not in used:
                    used.add(nm)
                    break
            lat = round(area["lat"] + RNG.uniform(-0.006, 0.006), 6)
            lng = round(area["lng"] + RNG.uniform(-0.006, 0.006), 6)
            n = len(outlets) + 1
            body = {"name": nm, "contact_number": f"+91999900{n:04d}", "contact_person": CONTACTS[n % len(CONTACTS)],
                    "address": f"Shop {n}, {area['name']}, Demo City (fictional)", "location": {"latitude": lat, "longitude": lng},
                    "geofence_radius_m": 100, "outlet_code": f"DEMO-{n:04d}", "territory_id": area["territory_id"], "area_id": area["id"],
                    "gst_number": f"09DEMO{n:04d}A1Z{n % 10}", "brands": RNG.sample(BRANDS, 2)}
            cu = (await c.call("POST", "/customers", ah, json=body)).json()
            await con.execute("insert into employee_customer_assignments (id,employee_id,customer_id,created_by,created_at) "
                              "select $1,$2,$3,(select id from users where email=$4),now()", uuid.uuid4(), uuid.UUID(emps[ai]["id"]), uuid.UUID(cu["id"]), cr["admin_email"])
            outlets.append({"id": cu["id"], "name": nm, "code": f"DEMO-{n:04d}", "lat": lat, "lng": lng, "area": area["name"],
                            "area_id": area["id"], "emp": ai, "brands": body["brands"]})
    print("outlets", len(outlets))

    # ---- FOS <-> Tally group mapping
    for em in emps:
        grp = f"{em['name']} - Demo Debtors"
        await con.execute("insert into fos_employee_mappings (id,raw_fos_name,employee_id,created_at,updated_at) values ($1,$2,$3,now(),now())",
                          uuid.uuid4(), grp, uuid.UUID(em["id"]))
        em["tally_group"] = grp

    c.st.update(areas=areas, emps=emps, outlets=outlets, territories=terr_ids)
    await tally_data(c)


async def tally_data(c: Ctx):
    """Synthetic Tally-style books (ledgers, sales bills, receipts, credit notes, open bills) posted through the
    real agent API of THIS fresh database by a purely synthetic agent. Nothing here can reach a real Tally."""
    ah, outlets, emps = c.tokens["admin"], c.st["outlets"], c.st["emps"]
    reg = (await c.call("POST", "/integrations/tally/agents", ah, json={
        "name": "DEMO Synthetic Tally Agent (no real Tally)", "tally_company_guid": COMPANY_GUID, "tally_company_name": COMPANY_NAME})).json()
    agent_h = {"X-Agent-Id": reg["agent"]["id"], "X-Agent-Key": reg["api_key"]}   # in memory only, never stored
    tally_outlets = [o for i, o in enumerate(outlets) if i % 12 != 11]            # 33 outlets have books; 3 are new (no ledger yet)
    advance_outlet = tally_outlets[30]["code"]                                     # an outlet with only an advance receipt
    invoices, receipts, notes = [], [], []
    n_inv = n_rct = n_cn = 0
    for oi, o in enumerate(tally_outlets):
        if o["code"] == advance_outlet:
            continue
        k = 3 + (oi % 5)
        picks = sorted(RNG.sample(DAYS_AGO, min(k, len(DAYS_AGO))), reverse=True)
        settled_outlet = oi % 7 == 3
        stuck_outlet = oi % 7 == 5
        for d in picks:
            n_inv += 1
            no = f"DEMO/26-27/{n_inv:05d}"
            amt = q(RNG.choice([1850, 3200, 4750.5, 6400, 8925.75, 12500, 15300, 21875.25, 9800, 27450, 36200, 48500.5]))
            idate = TODAY - timedelta(days=d)
            inv = dict(no=no, code=o["code"], date=idate, due=idate + timedelta(days=CREDIT_DAYS), amount=amt, brand=o["brands"][n_inv % 2], paid=Decimal("0"))
            invoices.append(inv)
            pay = 0
            if settled_outlet or (not stuck_outlet and d > 20 and RNG.random() < 0.55):
                pay = 2 if (settled_outlet or RNG.random() < 0.5) else 1
            if pay:
                paid = amt if pay == 2 else q(amt * Decimal(RNG.choice(["0.4", "0.5", "0.65"])))
                n_rct += 1
                rdate = min(idate + timedelta(days=RNG.randint(5, max(6, d - 2))), TODAY - timedelta(days=1))
                receipts.append(dict(no=f"DEMO/RCT/{n_rct:05d}", code=o["code"], date=rdate, amount=paid, bill=inv["no"],
                                     mode=RNG.choice(["CASH", "NEFT", "CHEQUE", "NEFT"]), onacct=False))
                inv["paid"] += paid
            if oi % 6 == 2 and d in (45, 58) and inv["amount"] - inv["paid"] > 0:       # a credit note against the bill
                cnamt = q((inv["amount"] - inv["paid"]) * Decimal("0.15"))
                n_cn += 1
                notes.append(dict(no=f"DEMO/CN/{n_cn:04d}", code=o["code"], date=min(idate + timedelta(days=12), TODAY - timedelta(days=1)), amount=cnamt, bill=inv["no"]))
                inv["paid"] += cnamt
    receipts.append(dict(no=f"DEMO/RCT/{n_rct + 1:05d}", code=advance_outlet, date=TODAY - timedelta(days=6), amount=q(5000), bill="", mode="NEFT", onacct=True))

    def ledger_name(code):
        return next(o["name"] for o in outlets if o["code"] == code)

    def group_of(code):
        o = next(o for o in outlets if o["code"] == code)
        return emps[o["emp"]]["tally_group"]

    closing = {o["code"]: Decimal("0") for o in tally_outlets}
    for i in invoices:
        closing[i["code"]] -= i["amount"]
    for r in receipts:
        closing[r["code"]] += r["amount"]
    for n in notes:
        closing[n["code"]] += n["amount"]
    ledgers = []
    for o in tally_outlets:
        em = emps[o["emp"]]
        ledgers.append(dict(guid=f"DEMO-LEDGER-{o['code']}", name=o["name"], parent=em["tally_group"], is_debtor=True, outlet_code=o["code"],
                            brand=o["brands"][0], address=f"{o['area']}, Demo City (fictional)", zone=next(a["territory"] for a in c.st["areas"] if a["id"] == o["area_id"]),
                            area=o["area"], is_bill_wise=True, credit_period=f"{CREDIT_DAYS} Days", opening_balance="0.00",
                            closing_balance=str(closing[o["code"]]), alter_id=1))
    snap = f"DEMO-LEDGERS-{SNAP}"
    res = (await c.call("POST", "/integrations/tally/sync/ledgers", headers=agent_h, json=dict(
        batch_id=snap, company_guid=COMPANY_GUID, snapshot_id=snap, is_final_chunk=True, as_of=datetime.now(timezone.utc).isoformat(),
        period_start="2026-04-01", ledgers=ledgers))).json()
    assert res["failed_count"] == 0, res
    print("ledgers", res["created_count"], res["updated_count"])

    vouchers, alter = [], 1000
    for i in invoices:
        alter += 1
        nm = ledger_name(i["code"])
        vouchers.append(dict(guid=f"DEMO-VCH-{i['no']}", alter_id=alter, date=i["date"].isoformat(), voucher_type="Sales", voucher_parent="Sales",
                             voucher_number=i["no"], party_ledger=nm, narration="Demo sales invoice (fictional)",
                             debtor_lines=[dict(ledger_name=nm, ledger_guid=f"DEMO-LEDGER-{i['code']}", amount=str(-i["amount"]), brand=i["brand"],
                                                bill_allocations=[dict(name=i["no"], bill_type="New Ref", amount=str(-i["amount"]), credit_period=f"{CREDIT_DAYS} Days")])],
                             counter_lines=[dict(ledger_name="DEMO Sales Account", ledger_class="OTHER", amount=str(i["amount"]))]))
    for r in receipts:
        alter += 1
        nm = ledger_name(r["code"])
        mode = r["mode"]
        if mode == "CASH":
            counter = dict(ledger_name="DEMO Cash", ledger_class="CASH", amount=str(-r["amount"]), bank_allocations=[dict(transaction_type="Cash", amount=str(-r["amount"]))])
        elif mode == "NEFT":
            counter = dict(ledger_name="DEMO Bank - Fictional Bank", ledger_class="BANK", amount=str(-r["amount"]),
                           bank_allocations=[dict(transaction_type="NEFT", instrument_number=f"DEMOUTR{alter}", bank_name="Fictional Bank", amount=str(-r["amount"]))])
        else:
            counter = dict(ledger_name="DEMO Bank - Fictional Bank", ledger_class="BANK", amount=str(-r["amount"]),
                           bank_allocations=[dict(transaction_type="Cheque", instrument_number=f"{alter:06d}", bank_name="Fictional Bank", amount=str(-r["amount"]))])
        alloc = [dict(name="", bill_type="On Account", amount=str(r["amount"]))] if r["onacct"] else \
                [dict(name=r["bill"], bill_type="Agst Ref", amount=str(r["amount"]))]
        vouchers.append(dict(guid=f"DEMO-VCH-{r['no']}", alter_id=alter, date=r["date"].isoformat(), voucher_type="Receipt", voucher_parent="Receipt",
                             voucher_number=r["no"], party_ledger=nm, narration="Demo receipt (fictional)",
                             debtor_lines=[dict(ledger_name=nm, ledger_guid=f"DEMO-LEDGER-{r['code']}", amount=str(r["amount"]), bill_allocations=alloc)],
                             counter_lines=[counter]))
    for n in notes:
        alter += 1
        nm = ledger_name(n["code"])
        vouchers.append(dict(guid=f"DEMO-VCH-{n['no']}", alter_id=alter, date=n["date"].isoformat(), voucher_type="Credit Note", voucher_parent="Credit Note",
                             voucher_number=n["no"], party_ledger=nm, narration="Demo credit note - rate difference (fictional)",
                             debtor_lines=[dict(ledger_name=nm, ledger_guid=f"DEMO-LEDGER-{n['code']}", amount=str(n["amount"]),
                                                bill_allocations=[dict(name=n["bill"], bill_type="Agst Ref", amount=str(n["amount"]))])],
                             counter_lines=[dict(ledger_name="DEMO Sales Returns", ledger_class="OTHER", amount=str(-n["amount"]))]))
    for k in range(0, len(vouchers), 200):
        res = (await c.call("POST", "/integrations/tally/sync/vouchers", headers=agent_h, json=dict(
            batch_id=f"DEMO-VOUCHERS-{SNAP}-{k}", company_guid=COMPANY_GUID, vouchers=vouchers[k:k + 200]))).json()
        assert res["failed_count"] == 0, res.get("errors", [])[:3]
    print("vouchers", len(vouchers), "(invoices", len(invoices), "receipts", len(receipts), "credit notes", len(notes), ")")

    bills = [dict(ledger_name=ledger_name(i["code"]), ledger_guid=f"DEMO-LEDGER-{i['code']}", bill_name=i["no"], bill_date=i["date"].isoformat(),
                  due_date=i["due"].isoformat(), pending_amount=str(-(i["amount"] - i["paid"])), overdue_days=max(0, (TODAY - i["due"]).days))
             for i in invoices if i["amount"] - i["paid"] > 0]
    bs = f"DEMO-BILLS-{SNAP}"
    res = (await c.call("POST", "/integrations/tally/sync/bills", headers=agent_h, json=dict(
        batch_id=bs, company_guid=COMPANY_GUID, snapshot_id=bs, as_of_date=TODAY.isoformat(), is_final_chunk=True, bills=bills))).json()
    assert res["failed_count"] == 0, res
    print("open bills", len(bills))
    c.st["billing"] = dict(invoices=[{**i, "date": i["date"].isoformat(), "due": i["due"].isoformat(), "amount": str(i["amount"]), "paid": str(i["paid"])} for i in invoices],
                           receipts=[{**r, "date": r["date"].isoformat(), "amount": str(r["amount"])} for r in receipts],
                           notes=[{**n, "date": n["date"].isoformat(), "amount": str(n["amount"])} for n in notes],
                           tally_codes=[o["code"] for o in tally_outlets])


async def main():
    which = (sys.argv[1] if len(sys.argv) > 1 else "A").upper()
    c = Ctx()
    await c.open()
    try:
        if which in ("A", "ALL"):
            await phase_a(c)
        if which in ("B", "ALL"):
            from seed_qa_demo_b import phase_b
            c.tokens.setdefault("admin", await c.login(c.cred["admin_email"], c.cred["admin_password"]))
            await phase_b(c)
        if which in ("C", "ALL"):
            from seed_qa_demo_c import phase_c
            c.tokens.setdefault("admin", await c.login(c.cred["admin_email"], c.cred["admin_password"]))
            await phase_c(c)
    finally:
        await c.close()


if __name__ == "__main__":
    asyncio.run(main())
