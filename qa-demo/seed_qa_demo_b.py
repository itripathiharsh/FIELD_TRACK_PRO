"""Phase B - historical field activity (past ~70 days), written directly (the API only accepts "today").

Everything is derived from phase A so it stays consistent:
  * visits go to each FOS's assigned outlets (plus a few ad-hoc visits outside assignment),
  * every historical field collection mirrors an existing Tally receipt (same outlet, date, amount) and is linked to it,
  * collections carry brand allocations taken from the bill they settle,
  * monthly plans / planned visits mirror the PLANNED visits (completed or missed),
  * work sessions (attendance) exist for every working day.
"""
from __future__ import annotations

import math
import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

IST = timezone(timedelta(hours=5, minutes=30))
HISTORY_DAYS = 70


def _ts(d: date, hh: int, mm: int) -> datetime:
    return datetime.combine(d, time(hh, mm), tzinfo=IST)


def _jitter(rng, lat, lng, metres):
    """A point within `metres` of (lat, lng)."""
    r = metres * math.sqrt(rng.random())
    th = rng.random() * 2 * math.pi
    return lat + (r * math.cos(th)) / 111_320, lng + (r * math.sin(th)) / (111_320 * math.cos(math.radians(lat)))


async def phase_b(c):
    import seed_qa_demo as m
    rng = m.RNG
    con, st = c.con, c.st
    emps, outlets, areas = st["emps"], st["outlets"], st["areas"]
    if await con.fetchval("select count(*) from visits"):
        raise SystemExit("STOPPED: visits already exist - recreate the build database first")
    admin_uid = await con.fetchval("select id from users where email=$1", c.cred["admin_email"])
    by_code = {o["code"]: o for o in outlets}
    start = m.TODAY - timedelta(days=HISTORY_DAYS)
    days = [start + timedelta(days=i) for i in range(HISTORY_DAYS) if (start + timedelta(days=i)).weekday() != 6]
    ydays = [d for d in days if d < m.TODAY]

    visits: dict[tuple, dict] = {}   # (emp_idx, outlet_code, date) -> visit

    def add_visit(ei, o, d, *, adhoc=False, status="COMPLETED", forced=False):
        key = (ei, o["code"], d)
        if key in visits:
            return visits[key]
        em = emps[ei]
        h = rng.randint(9, 16)
        mi = rng.randint(0, 59)
        sched = _ts(d, h, mi)
        v = dict(id=uuid.uuid4(), key=key, o=o, ei=ei, d=d, adhoc=adhoc, status=status, sched=sched, forced=forced,
                 creator=uuid.UUID(em["user_id"]) if adhoc else admin_uid)
        if status == "COMPLETED":
            ci = sched + timedelta(minutes=rng.randint(0, 18))
            v.update(ci=ci, co=ci + timedelta(minutes=rng.randint(12, 48)))
            v["ci_pt"] = _jitter(rng, o["lat"], o["lng"], 45)
            v["co_pt"] = _jitter(rng, o["lat"], o["lng"], 45)
        visits[key] = v
        return v

    # ---- 1. visits that carry a field collection: mirror Tally cash / cheque receipts
    tally_rcts = await con.fetch("""select p.id, p.customer_id, p.amount, p.payment_date, p.tally_voucher_guid, p.payment_method::text pm
                                    from payments p where p.source='TALLY' and p.tally_voucher_guid like 'DEMO-VCH-DEMO/RCT/%' order by p.payment_date""")
    cust_to_code = {uuid.UUID(o["id"]): o["code"] for o in outlets}
    billing = st["billing"]
    rct_meta = {f"DEMO-VCH-{r['no']}": r for r in billing["receipts"]}
    inv_brand = {i["no"]: i["brand"] for i in billing["invoices"]}
    collections = []
    for r in tally_rcts:
        meta = rct_meta.get(r["tally_voucher_guid"])
        if not meta or meta["mode"] == "NEFT" or meta["onacct"] or r["payment_date"] < start or r["payment_date"] >= m.TODAY:
            continue
        if rng.random() < 0.18:     # some receipts were keyed straight from the bank statement: no field collection
            continue
        code = cust_to_code[r["customer_id"]]
        o = by_code[code]
        pdate = r["payment_date"] if isinstance(r["payment_date"], date) and not isinstance(r["payment_date"], datetime) else r["payment_date"].astimezone(IST).date()
        if pdate.weekday() == 6:
            pdate -= timedelta(days=1)
        v = add_visit(o["emp"], o, pdate, forced=True)
        collections.append(dict(rct=r, meta=meta, v=v, brand=inv_brand.get(meta["bill"]) or o["brands"][0], date=pdate))

    # ---- 2. everyday visits
    for ei, em in enumerate(emps):
        own = [o for o in outlets if o["emp"] == ei]
        terr_outlets = [o for o in outlets if o["emp"] != ei and (ei < 3) == (o["emp"] < 3)]
        for d in days:
            n_target = rng.randint(3, 5) if d < m.TODAY else 0
            tries = 0
            have = sum(1 for k in visits if k[0] == ei and k[2] == d)
            while have < n_target and tries < 20:
                tries += 1
                adhoc = rng.random() < 0.28
                o = rng.choice(own)
                outside = adhoc and rng.random() < 0.12
                if outside:
                    o = rng.choice(terr_outlets)
                status = "MISSED" if (not adhoc and rng.random() < 0.07) else "COMPLETED"
                before = len(visits)
                v = add_visit(ei, o, d, adhoc=adhoc, status=status)
                v["outside"] = outside
                if len(visits) > before:
                    have += 1

    # ---- 3. insert visits (+ geo logs)
    reasons = ["Payment follow-up", "New scheme briefing", "Stock check", "Customer request", "Order booking", "Display audit"]
    vrows, gl_rows = [], []
    for v in visits.values():
        o, ei = v["o"], v["ei"]
        adhoc = v["adhoc"]
        notes = None
        if v["status"] == "COMPLETED":
            notes = rng.choice(["Stock levels fine", "Owner asked for scheme details", "Payment promised next week", "New display installed",
                                "Competitor offer discussed", "Cheque collected", "Cash collected", "Order discussed"])
        vrows.append((v["id"], uuid.UUID(o["id"]), uuid.UUID(emps[ei]["id"]), v["sched"], v["status"],
                      v.get("ci"), v.get("ci_pt"), v.get("co"), v.get("co_pt"), v["creator"], v["sched"] - timedelta(days=1), notes,
                      "AD_HOC" if adhoc else "PLANNED", rng.choice(reasons) if adhoc else None,
                      ("Outside assigned outlets (same territory)" if v.get("outside") else None) if adhoc else None))
        if v["status"] == "COMPLETED":
            for kind, ts, pt in (("CHECK_IN", v["ci"], v["ci_pt"]), ("CHECK_OUT", v["co"], v["co_pt"])):
                dist = m_dist(o, pt)
                gl_rows.append((uuid.uuid4(), v["id"], ts, pt, round(dist, 2), True, None, kind))
            if rng.random() < 0.06:    # an earlier failed attempt (too far / poor GPS) before the successful check-in
                far = _jitter(rng, o["lat"], o["lng"], 420)
                gl_rows.append((uuid.uuid4(), v["id"], v["ci"] - timedelta(minutes=3), far, round(m_dist(o, far), 2), False,
                                "Location outside the allowed radius", "CHECK_IN"))
    await con.executemany(
        """insert into visits (id,customer_id,employee_id,scheduled_at,status,check_in_at,check_in_location,check_out_at,check_out_location,synced,
                               created_by,created_at,updated_at,check_in_received_at,check_out_received_at,notes,visit_type,adhoc_reason,adhoc_notes)
           values ($1,$2,$3,$4,$5::visit_status_enum,$6,ST_SetSRID(ST_MakePoint($7,$8),4326)::geography,$9,ST_SetSRID(ST_MakePoint($10,$11),4326)::geography,
                   true,$12,$13,$13,$6,$9,$14,$15::visit_type_enum,$16,$17)""",
        [(a, b, cc, d, s, ci, (pt_ci[1] if pt_ci else None), (pt_ci[0] if pt_ci else None), co, (pt_co[1] if pt_co else None), (pt_co[0] if pt_co else None),
          creator, created, notes, vt, ar, an)
         for (a, b, cc, d, s, ci, pt_ci, co, pt_co, creator, created, notes, vt, ar, an) in vrows])
    await con.executemany(
        """insert into geo_verification_logs (id,visit_id,attempted_at,device_location,distance_from_customer_m,is_valid,failure_reason,verification_type)
           values ($1,$2,$3,ST_SetSRID(ST_MakePoint($4,$5),4326)::geography,$6,$7,$8,$9::geo_verification_type_enum)""",
        [(i, vid, ts, pt[1], pt[0], dist, ok, why, kind) for (i, vid, ts, pt, dist, ok, why, kind) in gl_rows])
    print("historical visits", len(vrows), "geo logs", len(gl_rows))

    # ---- 4. field collections linked to Tally receipts
    crows, brows, nlinked = [], [], 0
    for col in collections:
        v, r, meta = col["v"], col["rct"], col["meta"]
        em = emps[v["ei"]]
        pid = uuid.uuid4()
        method = "CHEQUE" if meta["mode"] == "CHEQUE" else "CASH"
        amt = Decimal(str(r["amount"]))
        created = v["co"] if v.get("co") else v["sched"]
        crows.append((pid, v["id"], r["customer_id"], uuid.UUID(em["id"]), amt, method, col["date"],
                      f"{600000 + len(crows) * 7:06d}" if method == "CHEQUE" else None, "Fictional Bank" if method == "CHEQUE" else None,
                      f"Collected from outlet against {meta['bill']}", "VERIFIED", admin_uid, created + timedelta(days=1), uuid.UUID(em["user_id"]), created,
                      f"demo-hist-{pid}", r["id"], created + timedelta(days=1)))
        brows.append((uuid.uuid4(), pid, col["brand"], amt))
        nlinked += 1
    await con.executemany(
        """insert into payments (id,visit_id,customer_id,employee_id,amount,payment_method,payment_date,cheque_number,cheque_bank_name,notes,status,
                                 reviewed_by,reviewed_at,created_by,created_at,updated_at,source,idempotency_key,tally_receipt_payment_id,tally_linked_at,tally_linked_by,verified_note)
           values ($1,$2,$3,$4,$5,$6::payment_method_enum,$7,$8,$9,$10,$11::payment_status_enum,$12,$13,$14,$15,$15,'MANUAL',$16,$17,$18,$12,'Verified against receipt in Tally (demo)')""",
        crows)
    await con.executemany("insert into payment_brand_allocations (id,payment_id,brand,allocated_amount) values ($1,$2,$3,$4)", brows)
    print("field collections (verified, linked to Tally receipts)", nlinked)

    # ---- 4b. the accountant's collection queue: recent collections not yet verified / not yet keyed into Tally / rejected
    used_keys = {x["v"]["key"] for x in collections}
    recent = [v for v in visits.values() if v["status"] == "COMPLETED" and m.TODAY - timedelta(days=9) <= v["d"] < m.TODAY and v["key"] not in used_keys]
    rng.shuffle(recent)
    plan = ["PENDING_VERIFICATION"] * 7 + ["VERIFIED_UNLINKED"] * 5 + ["REJECTED"] * 2
    seen_c = set()
    q_rows, q_brand = [], []
    for kind in plan:
        v = next((x for x in recent if (x["o"]["code"], x["d"]) not in seen_c), None)
        if v is None:
            break
        recent.remove(v)
        seen_c.add((v["o"]["code"], v["d"]))
        em, o = emps[v["ei"]], v["o"]
        pid = uuid.uuid4()
        method = rng.choice(["CASH", "CASH", "CHEQUE", "ONLINE"])
        amt = Decimal(str(rng.choice([2500, 4800, 6150, 9200, 11750, 15400, 3300, 7800])))
        created = v["co"]
        status = "PENDING_VERIFICATION" if kind == "PENDING_VERIFICATION" else ("VERIFIED" if kind == "VERIFIED_UNLINKED" else "REJECTED")
        q_rows.append((pid, v["id"], uuid.UUID(o["id"]), uuid.UUID(em["id"]), amt, method, v["d"],
                       f"{610000 + len(q_rows) * 11:06d}" if method == "CHEQUE" else None, "Fictional Bank" if method == "CHEQUE" else None,
                       f"DEMOUTR{rng.randint(10**9, 10**10 - 1)}" if method == "ONLINE" else None,
                       "Collected at outlet (demo)", status, (admin_uid if status != "PENDING_VERIFICATION" else None),
                       (created + timedelta(days=1) if status != "PENDING_VERIFICATION" else None),
                       ("Amount does not match the slip (demo)" if status == "REJECTED" else None),
                       ("Verified, awaiting Tally entry (demo)" if status == "VERIFIED" else None),
                       uuid.UUID(em["user_id"]), created, f"demo-q-{pid}"))
        q_brand.append((uuid.uuid4(), pid, o["brands"][0], amt))
    await con.executemany(
        """insert into payments (id,visit_id,customer_id,employee_id,amount,payment_method,payment_date,cheque_number,cheque_bank_name,utr_reference,notes,status,
                                 reviewed_by,reviewed_at,rejection_reason,verified_note,created_by,created_at,updated_at,source,idempotency_key)
           values ($1,$2,$3,$4,$5,$6::payment_method_enum,$7,$8,$9,$10,$11,$12::payment_status_enum,$13,$14,$15,$16,$17,$18,$18,'MANUAL',$19)""", q_rows)
    await con.executemany("insert into payment_brand_allocations (id,payment_id,brand,allocated_amount) values ($1,$2,$3,$4)", q_brand)
    print("collection queue items", len(q_rows))

    # ---- 5. monthly plans + planned visits mirroring the PLANNED visits
    plans: dict[tuple, uuid.UUID] = {}
    prows = []
    for v in visits.values():
        if v["adhoc"]:
            continue
        ei = v["ei"]
        key = (ei, v["d"].year, v["d"].month)
        if key not in plans:
            plans[key] = uuid.uuid4()
        prows.append((uuid.uuid4(), plans[key], uuid.UUID(emps[ei]["id"]), uuid.UUID(v["o"]["id"]), v["d"],
                      "COMPLETED" if v["status"] == "COMPLETED" else "MISSED", rng.choice(["LOW", "MEDIUM", "MEDIUM", "HIGH"]),
                      rng.choice(["Payment follow-up", "Scheme briefing", "Stock check", "Order booking"])))
    await con.executemany(
        "insert into monthly_visit_plans (id,employee_id,year,month,status,notes,created_by,created_at,updated_at) values ($1,$2,$3,$4,$5::monthly_plan_status_enum,$6,$7,now(),now())",
        [(pid, uuid.UUID(emps[k[0]]["id"]), k[1], k[2], "ACTIVE" if (k[1], k[2]) == (m.TODAY.year, m.TODAY.month) else "LOCKED", "Demo monthly beat plan", admin_uid)
         for k, pid in plans.items()])
    await con.executemany(
        """insert into planned_visits (id,monthly_plan_id,employee_id,customer_id,planned_date,visit_type,priority,notes,status,created_at,updated_at)
           values ($1,$2,$3,$4,$5,'PLANNED'::visit_type_enum,$6::priority_enum,$7,$8::planned_visit_status_enum,now(),now())""",
        # columns: id, plan, employee, customer, date, priority, notes, status   (prows: id, plan, emp, cust, date, status, priority, note)
        [(x[0], x[1], x[2], x[3], x[4], x[6], x[7], x[5]) for x in prows])
    print("monthly plans", len(plans), "planned visits", len(prows))

    # ---- 6. work sessions (attendance)
    wrows = []
    for ei, em in enumerate(emps):
        a = em["area"]
        for d in ydays:
            if rng.random() < 0.04:      # occasional leave day
                continue
            s_pt = _jitter(rng, a["lat"], a["lng"], 300)
            e_pt = _jitter(rng, a["lat"], a["lng"], 300)
            wrows.append((uuid.uuid4(), uuid.UUID(em["id"]), d, _ts(d, 9, rng.randint(0, 40)), s_pt[0], s_pt[1], round(rng.uniform(6, 20), 1),
                          _ts(d, 17, rng.randint(15, 59)), e_pt[0], e_pt[1], round(rng.uniform(6, 20), 1)))
    await con.executemany(
        """insert into employee_work_sessions (id,employee_id,work_date,status,start_time,start_latitude,start_longitude,start_accuracy_meters,
                                               end_time,end_latitude,end_longitude,end_accuracy_meters,created_at,updated_at)
           values ($1,$2,$3,'COMPLETED'::work_session_status_enum,$4,$5,$6,$7,$8,$9,$10,$11,now(),now())""", wrows)
    print("work sessions", len(wrows))


def m_dist(o, pt):
    lat, lng = pt
    dy = (lat - o["lat"]) * 111_320
    dx = (lng - o["lng"]) * 111_320 * math.cos(math.radians(o["lat"]))
    return math.hypot(dx, dy)
