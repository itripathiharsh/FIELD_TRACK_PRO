"""Phase C - live workflows through the REAL API (employees + admin), so notifications, geo logs, media, approvals and
order records are produced by the application itself. All people, outlets and amounts are fictional.
Core steps must succeed; optional ones print a WARNING and continue."""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def iso(delta_s=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=delta_s)).isoformat()


def fix(o, lat_off=0.0, lng_off=0.0, acc=9.0, mock=False, key=None):
    return {"latitude": o["lat"] + lat_off, "longitude": o["lng"] + lng_off, "accuracy_m": acc, "is_mock_location": mock,
            "captured_at": iso(-4), "idempotency_key": key or f"demo-{uuid.uuid4().hex[:14]}"}


async def phase_c(c):
    import seed_qa_demo as m
    rng, st, con = m.RNG, c.st, c.con
    ah = c.tokens["admin"]
    emps, outlets = st["emps"], st["outlets"]
    by_id = {o["id"]: o for o in outlets}
    warn = []

    async def opt(label, coro):
        try:
            return await coro
        except Exception as ex:  # noqa: BLE001
            warn.append(f"{label}: {str(ex)[:260]}")
            print("WARNING", label, "->", str(ex)[:260])
            return None

    # ---- employee sessions
    et = []
    for em in emps:
        et.append(await c.login(em["email"], c.cred["employee_password"]))
    own = {i: [o for o in outlets if o["emp"] == i] for i in range(len(emps))}
    print("employees logged in:", len(et))

    # ---- admin assigns today's beat (3 visits per FOS)
    visit_ids: dict[tuple, str] = {}
    for i, em in enumerate(emps):
        for k, o in enumerate(own[i][:3]):
            r = await c.call("POST", "/visits", ah, json={"customer_id": o["id"], "employee_id": em["id"], "scheduled_at": iso(300 + k * 4200)})
            visit_ids[(i, k)] = r.json()["id"]
    print("today's visits assigned:", len(visit_ids))

    # ---- workday start
    for i, em in enumerate(emps):
        a = em["area"]
        await opt(f"workday start {i}", c.call("POST", "/workday/start", et[i], json={"latitude": a["lat"], "longitude": a["lng"], "accuracy_meters": 12.0,
                                                                                    "client_timestamp": iso(), "notes": "Starting beat (demo)"}))

    async def checkin(i, k, **kw):
        o = own[i][k]
        return await c.call("POST", f"/visits/{visit_ids[(i, k)]}/check-in", et[i], json=fix(o, **kw), ok=None)

    async def checkout(i, k, note):
        o = own[i][k]
        return await c.call("POST", f"/visits/{visit_ids[(i, k)]}/check-out", et[i], json={**fix(o), "notes": note})

    async def photo(i, k, label, tone):
        return await c.call("POST", f"/visits/{visit_ids[(i, k)]}/media", et[i], files={"file": (f"{label}.jpg", m.jpeg(label, tone=tone), "image/jpeg")},
                            params={"note": label})

    async def requirement(i, k, items, rtype="Stock Replenishment", note=""):
        o = own[i][k]
        body = {"customer_id": o["id"], "visit_id": visit_ids[(i, k)], "requirement_type": rtype, "notes": note or "Demo requirement",
                "brand": items[0][0], "items": [{"brand_name": b, "product_model": pm, "requested_quantity": q, "expected_rate": rate} for (b, pm, q, rate) in items]}
        return (await c.call("POST", "/requirements", et[i], json=body)).json()

    async def pay(i, k, amount, method, brand, **kw):
        body = {"visit_id": visit_ids[(i, k)], "amount": str(amount), "payment_method": method, "payment_date": m.TODAY.isoformat(),
                "allocations": [{"brand": brand, "amount": str(amount)}], "idempotency_key": f"demo-pay-{uuid.uuid4().hex[:12]}", **kw}
        return (await c.call("POST", "/payments", et[i], json=body)).json()

    reqs, pays = [], []

    # E0 Aarav - a full completed visit: photo, requirement, cash collection
    o = own[0][0]
    r = await checkin(0, 0)
    assert r.status_code == 200, r.text
    await photo(0, 0, "Shop front", 0)
    await photo(0, 0, "Shelf display", 1)
    reqs.append(await requirement(0, 0, [("USHA", "Ceiling Fan 1200mm", 20, 1450.0), ("USHA", "Table Fan 400mm", 12, 1980.0)], note="Festive season stock"))
    pays.append(await pay(0, 0, "6500.00", "CASH", o["brands"][0], notes="Cash collected at outlet"))
    await checkout(0, 0, "Collected cash, requirement raised for ceiling fans")

    # E1 Diya - GPS / geofence scenarios (failed far check-in, mock location, then valid check-in, left in progress)
    far = await checkin(1, 0, lat_off=0.0046)
    mock = await checkin(1, 0, mock=True)
    print("geofence scenarios:", far.status_code, mock.status_code, "(expected 422 / 422)")
    r = await checkin(1, 0)
    assert r.status_code == 200, r.text
    await photo(1, 0, "Outlet board", 2)

    # E2 Kabir - cheque collection with proof + an ad-hoc visit to an outlet outside his assignment
    o2 = own[2][0]
    r = await checkin(2, 0)
    assert r.status_code == 200, r.text
    cq = await pay(2, 0, "12500.00", "CHEQUE", o2["brands"][0], cheque_number="410552", cheque_bank_name="Fictional Bank", notes="Cheque dated today")
    pays.append(cq)
    await opt("cheque proof", c.call("POST", f"/payments/{cq['id']}/proof", et[2], files={"file": ("cheque.jpg", m.jpeg("Cheque 410552", tone=3), "image/jpeg")}))
    await checkout(2, 0, "Cheque collected")
    outside = next(x for x in outlets if x["emp"] == 3)
    adh = await c.call("POST", "/visits/ad-hoc", et[2], json={"customer_id": outside["id"], "adhoc_reason": "Customer request", "adhoc_notes": "Owner called, outside my beat"})
    avid = adh.json()["id"]
    r = await c.call("POST", f"/visits/{avid}/check-in", et[2], json=fix(outside), ok=None)
    if r.status_code == 200:
        await c.call("POST", f"/visits/{avid}/check-out", et[2], json={**fix(outside), "notes": "Ad-hoc visit done"})

    # E3 Meera - requirement (will be partially approved), outlet proof + location correction proposal
    o3 = own[3][0]
    r = await checkin(3, 0)
    assert r.status_code == 200, r.text
    reqs.append(await requirement(3, 0, [("Havells", "LED Bulb 9W (pack of 10)", 40, 620.0), ("Havells", "Geyser 15L", 6, 7400.0)], note="Needs delivery before weekend"))
    await checkout(3, 0, "Requirement raised")
    async def outlet_proof(i, o, off, label, tone):
        """A live outlet photo + GPS fix. Taken AT the outlet it is auto-confirmed; taken ~400 m away it becomes a
        change request that an admin must approve or reject."""
        return await opt(f"outlet proof {label}", c.call("POST", "/customers/outlet-proofs", et[i], data={
            "latitude": o["lat"] + off, "longitude": o["lng"], "accuracy_m": 8, "is_mock_location": "false", "captured_at": iso(-3),
            "idempotency_key": f"demo-proof-{uuid.uuid4().hex[:10]}", "customer_id": o["id"], "device_info": "Demo phone"},
            files={"photo": (f"{label}.jpg", m.jpeg(label, tone=tone), "image/jpeg")}))

    await outlet_proof(3, o3, 0.0, "Outlet proof at shop", 0)                       # auto-confirmed
    proof_ok = await outlet_proof(3, own[3][2], 0.0036, "Outlet proof (moved)", 1)    # pending -> approved by admin
    proof_no = await outlet_proof(3, own[3][3], 0.0040, "Outlet proof (blurry)", 2)   # pending -> rejected by admin
    await outlet_proof(3, own[3][4], 0.0038, "Outlet proof (awaiting review)", 3)     # stays pending for the accountant
    proof = proof_ok
    prop = await opt("location proposal", c.call("POST", f"/customers/{own[3][1]['id']}/location-proposals", et[3], json={
        "proposed_latitude": own[3][1]["lat"] + 0.0004, "proposed_longitude": own[3][1]["lng"] + 0.0003, "gps_accuracy_meters": 9, "notes": "Shop moved to the main road"}))

    await opt("location proposal (left pending)", c.call("POST", f"/customers/{own[3][5]['id']}/location-proposals", et[3], json={
        "proposed_latitude": own[3][5]["lat"] - 0.0006, "proposed_longitude": own[3][5]["lng"] - 0.0002, "gps_accuracy_meters": 11, "notes": "GPS pin was on the wrong lane"}))

    # E4 Rohan - new outlet (prospect) with proof + field exception
    unattached = await opt("proof for new outlet", c.call("POST", "/customers/outlet-proofs", et[4], data={
        "latitude": 26.4202, "longitude": 80.3402, "accuracy_m": 10, "is_mock_location": "false", "captured_at": iso(-3), "idempotency_key": f"demo-newproof-{uuid.uuid4().hex[:8]}"},
        files={"photo": ("new.jpg", m.jpeg("New outlet front", tone=4), "image/jpeg")}))
    if unattached:
        await opt("prospect", c.call("POST", "/customers/prospect", et[4], json={
            "name": "Greenfield Gadgets (new)", "contact_number": "+919999009001", "contact_person": "Ishaan Dutta", "address": "Plot 9, Orchard Lane, Demo City (fictional)",
            "territory_id": emps[4]["area"]["territory_id"], "area_id": emps[4]["area"]["id"], "brands": ["Havells", "VU"],
            "location": {"latitude": 26.4202, "longitude": 80.3402}, "gps_accuracy_meters": 10, "outlet_proof_id": unattached.json()["id"],
            "notes": "New shop opened, wants Havells + VU"}))
    await opt("field exception", c.call("POST", "/field-exceptions", et[4], json={
        "visit_id": visit_ids[(4, 0)], "customer_id": own[4][0]["id"], "exception_type": "OUTLET_CLOSED", "description": "Shutter down, owner away (demo)"}))

    # E5 Tara - online payment + a second cheque, left pending for admin verification
    o5 = own[5][0]
    r = await checkin(5, 0)
    assert r.status_code == 200, r.text
    pays.append(await pay(5, 0, "8200.00", "ONLINE", o5["brands"][0], utr_reference="DEMOUTR94822117", notes="UPI transfer shown on phone"))
    pays.append(await pay(5, 0, "3150.00", "CASH", o5["brands"][1], notes="Small cash collection"))
    await checkout(5, 0, "Two collections recorded")

    # ---- more requirements on today's visits (variety of outcomes)
    reqs.append(await requirement(0, 1, [("Zebronics", "Soundbar 2.1", 8, 3200.0)], rtype="New Scheme Stock", note="Customer wants soundbars"))
    reqs.append(await requirement(5, 1, [("VU", "43in Smart TV", 3, 21500.0), ("VU", "32in Smart TV", 4, 11900.0)], note="Showroom refresh"))
    reqs.append(await requirement(4, 1, [("Anchor", "Switch Plate Set", 60, 185.0)], rtype="Stock Replenishment", note="Low stock"))

    # ---- extra requirements raised from the outlet (no visit needed) for a wider approval queue
    async def req_direct(i, k, items, rtype, note):
        o = own[i][k]
        body = {"customer_id": o["id"], "requirement_type": rtype, "notes": note, "brand": items[0][0],
                "items": [{"brand_name": b, "product_model": pm, "requested_quantity": q_, "expected_rate": rate} for (b, pm, q_, rate) in items]}
        return (await c.call("POST", "/requirements", et[i], json=body)).json()

    reqs.append(await req_direct(1, 2, [("Finolex", "FR Wire 1.5sqmm 90m", 25, 1850.0), ("Finolex", "PVC Pipe 25mm", 40, 310.0)], "Stock Replenishment", "Contractor demand"))
    reqs.append(await req_direct(2, 2, [("Zebronics", "Bluetooth Speaker", 15, 1290.0)], "New Scheme Stock", "Diwali scheme"))
    reqs.append(await req_direct(3, 2, [("Havells", "Mixer Grinder 750W", 10, 3450.0)], "Stock Replenishment", "Out of stock"))
    reqs.append(await req_direct(4, 3, [("USHA", "Iron Box", 18, 780.0), ("USHA", "Induction Cooktop", 6, 2600.0)], "Stock Replenishment", "Weekly refill"))
    reqs.append(await req_direct(0, 4, [("VU", "55in Smart TV", 2, 36900.0)], "Display Unit", "Showroom display unit"))
    reqs.append(await req_direct(5, 3, [("Anchor", "Modular Switch 6A", 120, 95.0)], "Stock Replenishment", "Contractor order"))

    # ---- more visit photographs
    await opt("photo E2", photo(2, 0, "Counter display", 3))
    await opt("photo E3", photo(3, 0, "Stock room", 4))
    await opt("photo E5", photo(5, 0, "New scheme poster", 1))
    await opt("photo E0b", photo(0, 0, "Competitor display", 2))

    # ---- two more new-outlet prospects: one stays pending, one is rejected
    async def prospect(i, name, phone, lat, lng, tone):
        pr = await opt(f"proof {name}", c.call("POST", "/customers/outlet-proofs", et[i], data={
            "latitude": lat, "longitude": lng, "accuracy_m": 9, "is_mock_location": "false", "captured_at": iso(-3),
            "idempotency_key": f"demo-np-{uuid.uuid4().hex[:10]}"}, files={"photo": ("new.jpg", m.jpeg(name, tone=tone), "image/jpeg")}))
        if not pr:
            return None
        return await opt(f"prospect {name}", c.call("POST", "/customers/prospect", et[i], json={
            "name": name, "contact_number": phone, "contact_person": "Owner (fictional)", "address": "Demo Market, Demo City (fictional)",
            "territory_id": emps[i]["area"]["territory_id"], "area_id": emps[i]["area"]["id"], "brands": ["Anchor", "Havells"],
            "location": {"latitude": lat, "longitude": lng}, "gps_accuracy_meters": 9, "outlet_proof_id": pr.json()["id"], "notes": "Demo prospect"}))

    p_pending = await prospect(1, "Silverline Home Needs (new)", "+919999009002", 26.4932, 80.3052, 1)
    p_reject = await prospect(2, "Corner Cell Point (new)", "+919999009003", 26.4801, 80.2931, 2)

    # ---- admin decisions on requirements -> orders
    async def decide(rq, action, **body):
        return await opt(f"requirement {action}", c.call("POST", f"/requirements/{rq['id']}/{action}", ah, json=body or None))

    await decide(reqs[0], "approve", admin_notes="Approved in full")
    await decide(reqs[1], "partially-approve", admin_notes="Approving 60% - limited stock", approved_quantity=28)
    await decide(reqs[2], "reject", admin_notes="Scheme not valid for this outlet")
    await decide(reqs[3], "approve", admin_notes="Approved")
    co = await decide(reqs[3], "confirm-order", admin_notes="Order confirmed (demo; nothing sent to any Tally)")
    await decide(reqs[0], "confirm-order", admin_notes="Order confirmed (demo)")
    # reqs[4], reqs[5] stay PENDING for the accountant to action

    # ---- admin: collections verification, rejection, receipt link, proofs, exceptions, prospects
    async def verify(p, **kw):
        return await opt("verify payment", c.call("POST", f"/payments/{p['id']}/verify", ah, json=kw or {}))

    await verify(pays[0], verified_note="Cash handed over to office (demo)")
    await verify(pays[1], bank_reference="CHQ410552", verified_note="Cheque deposited (demo)")
    await opt("reject payment", c.call("POST", f"/payments/{pays[3]['id']}/reject", ah, json={"rejection_reason": "Amount does not match the receipt slip (demo)"}))
    # pays[2] (online UTR) stays PENDING_VERIFICATION for the accountant

    # link the verified cash collection to a not-yet-linked Tally receipt of the same outlet, if one exists
    rc = await con.fetchrow("""select p.id from payments p join customers cu on cu.id=p.customer_id
                               where p.source='TALLY' and p.customer_id=$1 and p.id not in (select tally_receipt_payment_id from payments where tally_receipt_payment_id is not null)
                               order by p.payment_date desc limit 1""", uuid.UUID(pays[0]["customer_id"]) if "customer_id" in pays[0] else uuid.UUID(own[0][0]["id"]))
    if rc:
        await opt("link tally receipt", c.call("POST", f"/payments/{pays[0]['id']}/link-tally-receipt", ah, json={"tally_receipt_payment_id": str(rc["id"])}))

    if proof_ok:
        await opt("approve proof", c.call("POST", f"/customers/outlet-proofs/{proof_ok.json()['id']}/approve", ah))
    if proof_no:
        await opt("reject proof", c.call("POST", f"/customers/outlet-proofs/{proof_no.json()['id']}/reject", ah, json={"reason": "Photo is blurry - please retake (demo)"}))
    if prop:
        await opt("approve location proposal", c.call("POST", f"/location-proposals/{prop.json()['id']}/approve", ah))
    exc = await con.fetchval("select id from field_exceptions order by created_at desc limit 1")
    if exc:
        await opt("review exception", c.call("PATCH", f"/field-exceptions/{exc}/review", ah, json={"status": "APPROVED", "admin_notes": "Reasonable - outlet closed (demo)"}))
    pr = await con.fetchval("select id from customer_prospects where name = $1", "Greenfield Gadgets (new)")
    if pr:
        await opt("approve prospect", c.call("POST", f"/customers/prospects/{pr}/approve", ah))

    rid = await con.fetchval("select id from customer_prospects where name = $1", "Corner Cell Point (new)") if p_reject else None
    if rid:
        await opt("reject prospect", c.call("POST", f"/customers/prospects/{rid}/reject", ah, json={"reason": "Duplicate of an existing outlet nearby (demo)"}))

    # ---- more requirement decisions (queue keeps NEW / PARTIALLY_APPROVED / REJECTED / CONVERTED variety)
    await decide(reqs[6], "approve", admin_notes="Approved")
    await decide(reqs[6], "confirm-order", admin_notes="Confirmed (demo)")
    await decide(reqs[7], "reject", admin_notes="Scheme closed (demo)")
    await decide(reqs[8], "partially-approve", admin_notes="Part supply only (demo)", approved_quantity=6)
    await decide(reqs[9], "approve", admin_notes="Approved")
    # reqs[4], [5], [10], [11] remain NEW for the accountant to action

    # ---- close the oldest reporting month (shows a finalized, locked period)
    per = await con.fetchrow("select id from monthly_reporting_periods order by period_year, period_month limit 1")
    if per:
        await opt("review period", c.call("GET", f"/reports/monthly-periods/{per['id']}/review", ah))
        await opt("finalize period", c.call("POST", f"/reports/monthly-periods/{per['id']}/finalize", ah, json={}))

    # ---- upcoming monthly plan (visible in "My Monthly Plan" / admin planning screens)
    month_end = (m.TODAY.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    span = (month_end - m.TODAY).days
    prios = ["HIGH", "MEDIUM", "LOW"]
    nplan = 0
    for i in range(len(emps)):
        for n in range(6):
            d = m.TODAY + timedelta(days=1 + (n * 2) % max(1, span))
            if d.weekday() == 6 or d > month_end:
                continue
            o = own[i][(n + 1) % len(own[i])]
            r = await opt(f"plan {i}/{n}", c.call("POST", "/visit-planning/visits", et[i], json={
                "customer_id": o["id"], "planned_date": d.isoformat(), "visit_type": "PLANNED", "priority": prios[n % 3], "notes": "Demo planned visit"}))
            nplan += 1 if r else 0
    print("upcoming planned visits:", nplan)

    # ---- visit-form template (checklist) - optional
    await opt("form template", c.call("POST", "/form-templates", ah, json={
        "name": "Outlet Visit Checklist (Demo)", "description": "Short checklist for the field team",
        "sections": [{"title": "Outlet check", "order_index": 0, "questions": [
            {"question_text": "Is the brand display visible?", "question_type": "YES_NO", "is_required": True, "order_index": 0},
            {"question_text": "Stock level rating", "question_type": "RATING", "is_required": False, "order_index": 1}]}]}))

    for w in warn:
        print("  warn:", w)
    c.st["warnings"] = warn
