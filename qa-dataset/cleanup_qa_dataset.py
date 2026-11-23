"""
Remove ONLY the LOCAL QA dataset created by generate_qa_dataset.py (fieldtrackpro_dev only).

    python -I "F:\\Field track pro v2 for test\\qa-dataset\\cleanup_qa_dataset.py"            # dry run: counts only
    python -I "F:\\Field track pro v2 for test\\qa-dataset\\cleanup_qa_dataset.py" --execute  # delete, one transaction

Every delete is restricted twice: the row id/outlet must be in qa_manifest.json AND carry the TEST-QA marker.
Keeps: the test employee 9999999999 (TEST-QA-01), its territory "TEST - Local QA", area "TEST QA Area" and the
three account-setup outlets TEST-QA-OUT-001..003. Refuses to run unless connected to 127.0.0.1:5432/fieldtrackpro_dev.
"""
import asyncio
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qa_common as qc  # noqa: E402
import asyncpg  # noqa: E402

EXECUTE = "--execute" in sys.argv


async def main():
    url = qc.db_url()
    qc.check_url(url)
    if not os.path.exists(qc.MANIFEST):
        qc.abort("no qa_manifest.json - nothing to clean")
    m = json.load(open(qc.MANIFEST, encoding="utf-8"))
    if m.get("database") != qc.EXPECTED_DB or m.get("marker") != "TEST-QA-":
        qc.abort("manifest is not a fieldtrackpro_dev TEST-QA manifest")
    ids = lambda key: [uuid.UUID(x) for x in m.get(key, [])]  # noqa: E731
    outlets, areas, planned, visits, payments = ids("outlet_ids"), ids("area_ids"), ids("planned_visit_ids"), ids("visit_ids"), ids("payment_ids")
    agent = uuid.UUID(m["agent_id"]) if m.get("agent_id") else None
    emp = uuid.UUID(qc.TEST_EMPLOYEE_ID)

    con = await asyncpg.connect(url)
    await qc.assert_local(con)
    # Only outlets that are both in the manifest and TEST-QA coded (never 001-003, never anything else).
    outlets = [r["id"] for r in await con.fetch(
        "select id from customers where id = any($1::uuid[]) and outlet_code like 'TEST-QA-OUT-%' and outlet_code > 'TEST-QA-OUT-003'", outlets)]
    test_user = await con.fetchval("select user_id from employees where id=$1 and employee_code='TEST-QA-01'", emp)

    proof_keys = [r["storage_key"] for r in await con.fetch(
        "select storage_key from outlet_proofs where customer_id = any($1::uuid[])", outlets)]
    steps = [
        ("notifications (test user, QA payments/visits)",
         "delete from notifications where user_id=$1 and (payment_id = any($2::uuid[]) or visit_id = any($3::uuid[]) or planned_visit_id = any($4::uuid[]))",
         (test_user, payments, visits, planned)),
        ("payment-invoice allocations",
         "delete from payment_invoice_allocations where payment_id in (select id from payments where customer_id = any($1::uuid[]) and (source_reference like 'TEST-QA-VCH-%' or id = any($2::uuid[])))",
         (outlets, payments)),
        ("payment brand allocations",
         "delete from payment_brand_allocations where payment_id in (select id from payments where customer_id = any($1::uuid[]) and (source_reference like 'TEST-QA-VCH-%' or id = any($2::uuid[])))",
         (outlets, payments)),
        ("unlink field collections from QA Tally receipts",
         "update payments set tally_receipt_payment_id = null where customer_id = any($1::uuid[]) and tally_receipt_payment_id is not null",
         (outlets,)),
        ("field collections (QA)", "delete from payments where id = any($1::uuid[]) and customer_id = any($2::uuid[]) and source='MANUAL'", (payments, outlets)),
        ("Tally receipts (QA)", "delete from payments where customer_id = any($1::uuid[]) and source_reference like 'TEST-QA-VCH-%'", (outlets,)),
        ("Tally invoices (QA)", "delete from invoices where customer_id = any($1::uuid[]) and source_reference like 'TEST-QA-VCH-%'", (outlets,)),
        ("ledger adjustments (QA)", "delete from tally_ledger_adjustments where customer_id = any($1::uuid[]) and source_reference like 'TEST-QA-VCH-%'", (outlets,)),
        ("open bills (QA snapshots)", "delete from tally_open_bills where snapshot_id like 'TEST-QA-%' and customer_id = any($1::uuid[])", (outlets,)),
        ("manifest guids (QA snapshots)", "delete from tally_manifest_guids where snapshot_id like 'TEST-QA-%'", ()),
        ("snapshot runs (QA)", "delete from tally_snapshot_runs where id like 'TEST-QA-%' and agent_id = $1", (agent,)),
        ("voucher index (QA)", "delete from tally_voucher_index where guid like 'TEST-QA-VCH-%'", ()),
        ("Tally audit rows (QA agent)", "delete from tally_audit_logs where agent_id = $1", (agent,)),
        ("debtor ledgers (QA)", "delete from tally_debtor_ledgers where tally_guid like 'TEST-QA-LEDGER-%' and customer_id = any($1::uuid[])", (outlets,)),
        ("customer brands (QA outlets)", "delete from customer_brands where customer_id = any($1::uuid[])", (outlets,)),
        ("geo logs of QA visits", "delete from geo_verification_logs where visit_id = any($1::uuid[])", (visits,)),
        ("visits (QA, test employee)", "delete from visits where id = any($1::uuid[]) and employee_id=$2 and customer_id = any($3::uuid[])", (visits, emp, outlets)),
        ("planned visits (QA)", "delete from planned_visits where id = any($1::uuid[]) and employee_id=$2 and notes like 'TEST-QA%'", (planned, emp)),
        ("empty monthly plans of the test employee",
         "delete from monthly_visit_plans p where p.employee_id=$1 and not exists (select 1 from planned_visits v where v.monthly_plan_id=p.id)", (emp,)),
        ("outlet location proofs (QA outlets: GPS test + onboarding)",
         "delete from outlet_proofs where customer_id = any($1::uuid[])", (outlets,)),
        ("legacy location proposals (QA outlets)",
         "delete from customer_location_proposals where customer_id = any($1::uuid[])", (outlets,)),
        ("outlet assignments (QA outlets)", "delete from employee_customer_assignments where customer_id = any($1::uuid[]) and employee_id=$2", (outlets, emp)),
        ("outlets (QA 004+)", "delete from customers where id = any($1::uuid[]) and outlet_code like 'TEST-QA-OUT-%'", (outlets,)),
        ("areas (QA, now empty)",
         "delete from areas a where a.id = any($1::uuid[]) and a.name ilike 'test qa %' and not exists (select 1 from customers c where c.area_id=a.id)", (areas,)),
        ("brands (TEST-QA, unused)",
         "delete from brands b where b.name ilike 'test-qa %' and not exists (select 1 from customer_brands cb where cb.brand_id=b.id) "
         "and not exists (select 1 from invoices i where i.brand_id=b.id) and not exists (select 1 from payment_brand_allocations x where x.brand_id=b.id)", ()),
        ("sync agent (QA)", "delete from sync_agents where id=$1 and name like 'TEST-QA %'", (agent,)),
    ]
    print(("EXECUTING" if EXECUTE else "DRY RUN"), "against", qc.EXPECTED_DB)
    tr = con.transaction()
    await tr.start()
    try:
        for label, sql, args in steps:
            await qc.assert_local(con)
            res = await con.execute(sql, *args)
            print(f"  {label}: {res}")
        if EXECUTE:
            await tr.commit()
            removed = 0
            for root in (os.path.join(qc.BACKEND_DIR, "media_storage"),
                         os.path.join(r"F:\Field track pro v2 for test\_wt_android_uiieldtrackpro-backend", "media_storage")):
                for key in proof_keys:
                    f = os.path.normpath(os.path.join(root, key))
                    if f.startswith(os.path.normpath(root) + os.sep) and os.path.isfile(f):
                        os.remove(f)
                        removed += 1
            print(f"  stored proof photos removed from disk: {removed}")
            os.replace(qc.MANIFEST, qc.MANIFEST + ".cleaned")
            print("committed; manifest renamed to qa_manifest.json.cleaned")
        else:
            await tr.rollback()
            print("dry run: rolled back (use --execute to delete)")
    except Exception:
        await tr.rollback()
        raise
    finally:
        await con.close()


asyncio.run(main())
