"""One-off patch: enrich the QA seeder queues (phase B collections queue; phase C requirements, photos, prospects, period close)."""
import ast
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------- phase B
p = HERE / "seed_qa_demo_b.py"
s = p.read_text(encoding="utf-8")
if "4b. the accountant's collection queue" not in s:
    marker = "    # ---- 5. monthly plans + planned visits mirroring the PLANNED visits"
    add = '''    # ---- 4b. the accountant's collection queue: recent collections not yet verified / not yet keyed into Tally / rejected
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

'''
    assert marker in s
    s = s.replace(marker, add + marker, 1)
    ast.parse(s)
    p.write_text(s, encoding="utf-8")

# ---------------------------------------------------------------- phase C
p = HERE / "seed_qa_demo_c.py"
s = p.read_text(encoding="utf-8")
if "extra requirements raised from the outlet" not in s:
    marker = "    # ---- admin decisions on requirements -> orders"
    add = '''    # ---- extra requirements raised from the outlet (no visit needed) for a wider approval queue
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

'''
    assert marker in s
    s = s.replace(marker, add + marker, 1)
    marker2 = "    # ---- upcoming monthly plan"
    add2 = '''    if p_reject:
        await opt("reject prospect", c.call("POST", f"/customers/prospects/{p_reject.json()['id']}/reject", ah, json={"reason": "Duplicate of an existing outlet nearby (demo)"}))

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

'''
    assert marker2 in s
    s = s.replace(marker2, add2 + marker2, 1)
    ast.parse(s)
    p.write_text(s, encoding="utf-8")
print("patched")
