"""
Agent 2.0: request builders (read-only, proven forms), parsers (synthetic and the
client's real exports when available), and the engine's load / checkpoint rules.
"""
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from tally_sync_agent.core.checkpoint_manager import CheckpointManager
from tally_sync_agent.core.backend_client import DryRunBackend
from tally_sync_agent.core.quarantine_store import QuarantineStore
from tally_sync_agent.core.retry_queue import RetryQueue
from tally_sync_agent.engine import sync_engine_v2 as E
from tally_sync_agent.extractors import tally_xml as tx
from tally_sync_agent.extractors import v2_extractors as X
from incremental_adapter import IncrementalFromChanged  # 2.2.1 month/day incremental for 2.2.0 fakes

REAL = Path(os.environ.get("TALLY_EXPORT_DIR", r"C:\Users\Admin\Downloads"))


# ---------------------------------------------------------------------------
# Requests: export only, proven filter forms
# ---------------------------------------------------------------------------

def test_every_request_is_an_export_without_write_constructs():
    sc = tx.Scope(date(2026, 4, 1), date(2027, 3, 31), "SGRG SERVICES (OPC) PRIVATE LIMITED")
    reqs = [
        tx.voucher_request(tx.VOUCHER_FULL_FETCH, day=date(2026, 11, 13), scope=sc),
        tx.voucher_request(tx.VOUCHER_FULL_FETCH, min_alter_id=120406, date_from=date(2026, 11, 1), date_to=date(2026, 11, 18), scope=sc),
        tx.voucher_request(tx.MANIFEST_FETCH, day=date(2026, 4, 1), scope=sc),
        tx.debtors_request(scope=sc), tx.debtors_request(5, scope=sc), tx.all_ledgers_request(), tx.groups_request(),
        tx.voucher_types_request(), tx.creditors_request(scope=sc), tx.bills_payable_request(date(2026, 3, 31), books_from=date(2024, 4, 1)),
        tx.group_summary_request("Sundry Debtors", date(2025, 4, 1), date(2026, 3, 31)),
        tx.bills_receivable_request(date(2026, 3, 31), books_from=date(2024, 4, 1)),
    ]
    for r in reqs:
        assert "<TALLYREQUEST>Export</TALLYREQUEST>" in r
        low = r.lower()
        assert "import" not in low and "action=" not in low and "<function" not in low
    assert '$Date = $$Date:"13-Nov-2026"' in reqs[0] and '<SVFROMDATE TYPE="Date">13-Nov-2026</SVFROMDATE>' in reqs[0]
    assert "$$Number:$AlterId &gt; 120406" in reqs[1]
    assert "<CHILDOF>$$GroupSundryDebtors</CHILDOF>" in reqs[3] and "CHILDROF" not in reqs[3]
    assert '<SVTODATE TYPE="Date">31-Mar-2026</SVTODATE>' in reqs[-1] and "<ID>Bills Receivable</ID>" in reqs[-1]


# ---------------------------------------------------------------------------
# Synthetic parsing
# ---------------------------------------------------------------------------

GROUPS = """<ENVELOPE><GROUP NAME="Sundry Debtors" RESERVEDNAME="Sundry Debtors"><PARENT>Current Assets</PARENT></GROUP>
<GROUP NAME="Debtors Oppo" RESERVEDNAME=""><PARENT>Sundry Debtors</PARENT></GROUP>
<GROUP NAME="Bank Accounts" RESERVEDNAME="Bank Accounts"><PARENT>Current Assets</PARENT></GROUP>
<GROUP NAME="Bank OD A/c" RESERVEDNAME="Bank OD A/c"><PARENT>Loans (Liability)</PARENT></GROUP>
<GROUP NAME="Cash-in-Hand" RESERVEDNAME="Cash-in-Hand"><PARENT>Current Assets</PARENT></GROUP></ENVELOPE>"""
LEDGERS = """<ENVELOPE><LEDGER NAME="Shop A"><PARENT>Debtors Oppo</PARENT><GUID>G-A</GUID></LEDGER>
<LEDGER NAME="Shop B"><PARENT>Sundry Debtors</PARENT><GUID>G-B</GUID></LEDGER>
<LEDGER NAME="HDFC"><PARENT>Bank Accounts</PARENT><GUID>G-H</GUID></LEDGER>
<LEDGER NAME="UCO OD"><PARENT>Bank OD A/c</PARENT><GUID>G-U</GUID></LEDGER>
<LEDGER NAME="Cash"><PARENT>Cash-in-Hand</PARENT><GUID>G-C</GUID></LEDGER></ENVELOPE>"""
DEBTORS = """<ENVELOPE><LEDGER NAME="Shop A"><GUID>G-A</GUID><PARENT>Debtors Oppo</PARENT><ALTERID> 7</ALTERID>
<OPENINGBALANCE>-1000.00</OPENINGBALANCE><CLOSINGBALANCE>-1500.00</CLOSINGBALANCE><ISBILLWISEON>Yes</ISBILLWISEON>
<LANGUAGENAME.LIST><NAME.LIST><NAME>Shop A</NAME><NAME>UPDD00671234</NAME></NAME.LIST></LANGUAGENAME.LIST></LEDGER>
<LEDGER NAME="Shop B"><GUID>G-B</GUID><PARENT>Sundry Debtors</PARENT><OPENINGBALANCE></OPENINGBALANCE></LEDGER></ENVELOPE>"""
VTYPES = """<ENVELOPE><VOUCHERTYPE NAME="Sales"><PARENT>Sales</PARENT></VOUCHERTYPE>
<VOUCHERTYPE NAME="Oppo"><PARENT>Sales</PARENT></VOUCHERTYPE>
<VOUCHERTYPE NAME="Receipt"><PARENT>Receipt</PARENT></VOUCHERTYPE>
<VOUCHERTYPE NAME="BANK RECEIPT"><PARENT>Receipt</PARENT></VOUCHERTYPE></ENVELOPE>"""


def _masters():
    return X.parse_masters(*(ET.fromstring(x) for x in (GROUPS, LEDGERS, DEBTORS, VTYPES)))


def test_masters_aliases_codes_balances_and_classes():
    m = _masters()
    a = m.debtors["shop a"]
    assert a["aliases"] == ["UPDD00671234"] and a["outlet_code"] == "UPDD00671234"
    assert a["opening_balance"] == "-1000.00" and a["closing_balance"] == "-1500.00" and a["is_bill_wise"] is True
    assert m.debtors["shop b"]["opening_balance"] == "0", "blank balance = zero, as Tally shows it"
    assert [m.ledger_class(n) for n in ("Shop A", "Shop B", "HDFC", "UCO OD", "Cash")] == ["DEBTOR", "DEBTOR", "BANK", "BANK", "CASH"]
    assert m.voucher_parent["Oppo"] == "Sales" and m.voucher_parent["BANK RECEIPT"] == "Receipt"
    snap = X.ledger_snapshot_items(m)
    assert {i["name"]: i["is_debtor"] for i in snap} == {"Shop A": True, "Shop B": True, "HDFC": False, "UCO OD": False, "Cash": False}


RECEIPT = """<ENVELOPE><TALLYMESSAGE><VOUCHER VCHTYPE="BANK RECEIPT"><DATE>20261113</DATE><GUID>V-1</GUID>
<NARRATION>BY TRANSFER-RTGS UTR NO: X</NARRATION><VOUCHERTYPENAME>BANK RECEIPT</VOUCHERTYPENAME><VOUCHERNUMBER>7858</VOUCHERNUMBER>
<ISCANCELLED>No</ISCANCELLED><ISOPTIONAL>No</ISOPTIONAL><ALTERID> 120406</ALTERID>
<ALLLEDGERENTRIES.LIST><LEDGERNAME>Shop A</LEDGERNAME><AMOUNT>250000.00</AMOUNT><BANKALLOCATIONS.LIST>      </BANKALLOCATIONS.LIST>
 <BILLALLOCATIONS.LIST><NAME>SGRG/KNP/3148</NAME><BILLTYPE>Agst Ref</BILLTYPE><AMOUNT>80829.76</AMOUNT></BILLALLOCATIONS.LIST>
 <BILLALLOCATIONS.LIST><NAME></NAME><BILLTYPE>On Account</BILLTYPE><AMOUNT>169170.24</AMOUNT></BILLALLOCATIONS.LIST>
 <BILLALLOCATIONS.LIST>      </BILLALLOCATIONS.LIST></ALLLEDGERENTRIES.LIST>
<ALLLEDGERENTRIES.LIST><LEDGERNAME>UCO OD</LEDGERNAME><AMOUNT>-250000.00</AMOUNT>
 <BANKALLOCATIONS.LIST><INSTRUMENTDATE>20261113</INSTRUMENTDATE><TRANSACTIONTYPE>Cheque/DD</TRANSACTIONTYPE>
 <INSTRUMENTNUMBER>001249</INSTRUMENTNUMBER><UNIQUEREFERENCENUMBER>5Z2Tu28Imgu1hGvS</UNIQUEREFERENCENUMBER>
 <PAYMENTMODE>Transacted</PAYMENTMODE><AMOUNT>-250000.00</AMOUNT></BANKALLOCATIONS.LIST></ALLLEDGERENTRIES.LIST>
<INVENTORYENTRIES.LIST><VOUCHER>0</VOUCHER></INVENTORYENTRIES.LIST>
</VOUCHER>
<VOUCHER VCHTYPE="Receipt"><DATE></DATE><VOUCHERTYPENAME>Receipt</VOUCHERTYPENAME><AMOUNT>5</AMOUNT></VOUCHER>
<VOUCHER VCHTYPE="Contra"><DATE>20261113</DATE><GUID>V-2</GUID><VOUCHERTYPENAME>Contra</VOUCHERTYPENAME>
<ALLLEDGERENTRIES.LIST><LEDGERNAME>HDFC</LEDGERNAME><AMOUNT>-5</AMOUNT></ALLLEDGERENTRIES.LIST>
<ALLLEDGERENTRIES.LIST><LEDGERNAME>Cash</LEDGERNAME><AMOUNT>5</AMOUNT></ALLLEDGERENTRIES.LIST></VOUCHER>
</TALLYMESSAGE></ENVELOPE>"""


def test_voucher_debtor_lines_bills_banks_and_rejections():
    good, bad = X.parse_vouchers(ET.fromstring(RECEIPT), _masters())
    assert [v["guid"] for v in good] == ["V-1", "V-2"]
    assert len(bad) == 1 and bad[0]["source_reference"] is None and "GUID" in bad[0]["validation_error"]
    v = good[0]
    assert v["voucher_parent"] == "Receipt" and v["alter_id"] == 120406 and v["narration"].startswith("BY TRANSFER")
    (line,) = v["debtor_lines"]
    assert line["ledger_guid"] == "G-A" and line["amount"] == "250000.00"
    assert [(b["name"], b["bill_type"], b["amount"]) for b in line["bill_allocations"]] == [
        ("SGRG/KNP/3148", "Agst Ref", "80829.76"), (None, "On Account", "169170.24")]
    assert line["bank_allocations"] == []
    (counter,) = v["counter_lines"]
    assert counter["ledger_class"] == "BANK"
    assert counter["bank_allocations"][0]["instrument_number"] == "001249"
    assert counter["bank_allocations"][0]["instrument_date"] == "2026-11-13"
    contra = good[1]
    assert contra["debtor_lines"] == [] and contra["counter_lines"] == [], "header only: lets FTP retire a reclassified voucher"


BILLS = """<ENVELOPE>
 <BILLFIXED><BILLDATE>1-Apr-25</BILLDATE><BILLREF>1</BILLREF><BILLPARTY>Shop A</BILLPARTY></BILLFIXED>
 <BILLFIXED1></BILLFIXED1><BILLFIXED5></BILLFIXED5><BILLCL>-118000.00</BILLCL><BILLDUE>16-Apr-25</BILLDUE><BILLOVERDUE>594</BILLOVERDUE>
 <BILLFIXED><BILLDATE>2-May-25</BILLDATE><BILLREF>2</BILLREF><BILLPARTY>Some Creditor</BILLPARTY></BILLFIXED>
 <BILLCL>-3.00</BILLCL><BILLDUE>2-May-25</BILLDUE><BILLOVERDUE>563</BILLOVERDUE>
</ENVELOPE>"""


def test_bills_receivable_parsed_for_debtors_only():
    bills = X.parse_bills_receivable(ET.fromstring(BILLS), _masters())
    assert bills == [{"bill_date": "2025-04-01", "bill_name": "1", "ledger_name": "Shop A", "pending_amount": "-118000.00",
                      "due_date": "2025-04-16", "overdue_days": 594, "ledger_guid": "G-A"}]


# ---------------------------------------------------------------------------
# The client's real exports (skipped where the files are not present)
# ---------------------------------------------------------------------------

def _real(name):
    p = REAL / name
    if not p.exists():
        pytest.skip(f"real export {name} not available")
    from tally_sync_agent.core.tally_client import TallyClient
    return ET.fromstring(TallyClient()._clean_xml(p.read_text(encoding="utf-8-sig", errors="replace")))


@pytest.fixture(scope="module")
def real_masters():
    return X.parse_masters(_real("02_groups.xml"), _real("03_all_ledgers.xml"), _real("04_debtors_today.xml"),
                           _real("09_voucher_types.xml"))


def test_real_masters_match_audit(real_masters):
    m = real_masters
    assert len(m.debtors) == 1595 and len(m.ledger_guid) == 1980
    debtor_by_group = {n for n, p in m.ledger_parent.items() if m.group_class.get(p) == "DEBTOR"}
    assert {d["name"] for d in m.debtors.values()} == debtor_by_group
    assert sum(1 for i in X.ledger_snapshot_items(m) if not i["is_debtor"]) == 385
    from_alias = [d for d in m.debtors.values() if d["outlet_code"] and d["outlet_code"] in [a.upper() for a in d["aliases"]]]
    assert len(from_alias) == 450
    assert m.voucher_parent["Performa Invoice"] == "Sales" and m.voucher_parent["Expenses"] == "Purchase"
    opening = sum(Decimal(d["opening_balance"]) for d in m.debtors.values())
    assert opening == Decimal("-119271508.94"), "Group Summary of Sundry Debtors as on 31-03-2026"


def test_real_one_day_vouchers(real_masters):
    good, bad = X.parse_vouchers(_real("B_wildcard_sublists.xml"), real_masters)
    assert len(good) == 122 and bad == []
    types = {}
    for v in good:
        types[v["voucher_parent"]] = types.get(v["voucher_parent"], 0) + 1
    assert types["Sales"] == 46 and types["Receipt"] == 49
    bills = [b for v in good for l in v["debtor_lines"] for b in l["bill_allocations"]]
    assert len(bills) == 149 and all(b["bill_type"] for b in bills)


def test_real_bills_receivable_totals(real_masters):
    today = X.parse_bills_receivable(_real("08_bills_receivable_today.xml"), real_masters)
    assert len(today) == 2586 and sum(Decimal(b["pending_amount"]) for b in today) == Decimal("-200138877.64")
    mar = X.parse_bills_receivable(_real("07_bills_receivable_31mar2026.xml"), real_masters)
    assert len(mar) == 1979 and sum(Decimal(b["pending_amount"]) for b in mar) == Decimal("-121206792.67")
    assert all(b["bill_date"] <= "2026-03-31" for b in mar)


# ---------------------------------------------------------------------------
# Engine: first full load, resume, checkpoints
# ---------------------------------------------------------------------------

class FakeSource(IncrementalFromChanged):
    def __init__(self, days):
        self.days = days  # date -> list of voucher payloads
        self.m = _masters()
        self.calls = []
        self.alter_ceiling = 100

    def masters(self, cached=None, debtor_min_alter=0, full_debtors=False):
        return self.m

    def day_manifest(self, d):
        self.calls.append(("manifest", d))
        return [v["guid"] for v in self.days.get(d, [])], self.alter_ceiling

    def range_manifest(self, a, b):
        self.calls.append(("range", a, b))
        return [(v["guid"], d.strftime("%Y%m%d"), self.alter_ceiling)
                for d, vs in sorted(self.days.items()) if a <= d <= b for v in vs]

    def day_vouchers(self, m, d):
        self.calls.append(("day", d))
        return list(self.days.get(d, [])), []

    def changed_vouchers(self, m, min_alter):
        self.calls.append(("changed", min_alter))
        return [v for vs in self.days.values() for v in vs if v["alter_id"] > min_alter], []

    def bills(self, m, as_of):
        return [{"ledger_name": "Shop A", "ledger_guid": "G-A", "bill_name": "1", "pending_amount": "-5"}]


class RecordingBackend:
    def __init__(self, fail_guids=()):
        self.calls = []
        self.fail = set(fail_guids)

    def heartbeat(self, **kw):
        self.calls.append(("heartbeat", kw))

    def sync_ledgers(self, batch_id, company_guid, ledgers, **kw):
        self.calls.append(("ledgers", len(ledgers), kw))
        return {"details": {}}

    def sync_bills(self, batch_id, company_guid, bills, **kw):
        self.calls.append(("bills", len(bills), kw))
        return {"details": {}}

    def sync_manifest(self, batch_id, company_guid, guids, **kw):
        self.calls.append(("manifest", sorted(guids), kw))
        return {"details": {"ok": True}}

    def sync_vouchers(self, batch_id, company_guid, vouchers):
        self.calls.append(("vouchers", [v["guid"] for v in vouchers]))
        errs = [{"identifier": v["guid"], "error": "ledger unknown"} for v in vouchers if v["guid"] in self.fail]
        return {"created_count": len(vouchers) - len(errs), "updated_count": 0, "retired_count": 0, "errors": errs}


def _engine(tmp_path, src, backend, today=date(2026, 4, 3)):
    db = tmp_path / "s.db"
    eng = E.SyncEngineV2(tally_client=object(), backend_client=backend, checkpoint_manager=CheckpointManager(db),
                         retry_queue=RetryQueue(db), quarantine_store=QuarantineStore(db), data_dir=tmp_path,
                         source=src, today=lambda: today)
    eng.period_start = date(2026, 4, 1)
    return eng


def _vp(guid, alter, d="2026-04-01"):
    return {"guid": guid, "alter_id": alter, "date": d, "voucher_type": "Sales", "voucher_parent": "Sales",
            "debtor_lines": [], "counter_lines": []}


def test_initial_load_day_by_day_manifest_union_and_checkpoint_m0(tmp_path):
    d1, d2, d3 = date(2026, 4, 1), date(2026, 4, 2), date(2026, 4, 3)
    src = FakeSource({d1: [_vp("A", 10)], d3: [_vp("C", 30, "2026-04-03")]})
    be = RecordingBackend()
    eng = _engine(tmp_path, src, be)
    # A voucher keyed in on day 2 after the pre-scan: the load still sees it and the manifest keeps it.
    real_day = src.day_vouchers
    src.day_vouchers = lambda m, d: ([_vp("B", 150, "2026-04-02")], []) if d == d2 else real_day(m, d)
    report = eng.initial_load("CMP")
    kinds = [c[0] for c in be.calls]
    assert kinds[:2] == ["ledgers", "bills"]
    assert [c for c in src.calls if c[0] in ("manifest", "range")] == [("range", d1, d3)], "one month request (2.0.1)"
    manifest = [c for c in be.calls if c[0] == "manifest"][0]
    assert manifest[1] == ["A", "B", "C"] and manifest[2]["is_final_chunk"] is True
    assert eng.checkpoints.get_checkpoint(E.CP_VOUCHERS)["last_alter_id"] == 100, "M0 from the pre-scan, not the max seen"
    assert report["vouchers"]["vouchers"] == 3


def test_initial_load_resumes_after_interruption(tmp_path):
    d1, d2 = date(2026, 4, 1), date(2026, 4, 2)
    src = FakeSource({d1: [_vp("A", 10)], d2: [_vp("B", 20, "2026-04-02")]})
    be = RecordingBackend()
    eng = _engine(tmp_path, src, be, today=d2)
    real = src.day_vouchers

    def boom(m, d):
        if d == d2:
            raise E.TallyConnectionError("Tally closed the connection")
        return real(m, d)
    src.day_vouchers = boom
    with pytest.raises(E.TallyConnectionError):
        eng.initial_load("CMP")
    state = json.loads((tmp_path / "initial_load_v2.json").read_text())
    assert state["loaded_through"] == "2026-04-01" and state["m0"] == 100
    src.day_vouchers = real
    src.calls.clear()
    eng2 = _engine(tmp_path, src, be, today=d2)
    eng2.initial_load("CMP")
    assert [c for c in src.calls if c[0] == "day"] == [("day", d2)], "day 1 is not read again"
    assert not [c for c in src.calls if c[0] in ("manifest", "range")], "the pre-scan is not repeated"


def test_incremental_checkpoint_capped_by_rejected_voucher_until_accepted(tmp_path):
    src = FakeSource({date(2026, 4, 1): [_vp("A", 101), _vp("B", 102), _vp("C", 103)]})
    be = RecordingBackend(fail_guids={"B"})
    eng = _engine(tmp_path, src, be)
    eng.masters = src.m
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=100)
    r = eng.incremental_vouchers("CMP")
    assert r["failed"] == 1 and r["checkpoint"] == 101, "never advances past the rejected voucher"
    be.fail.clear()
    r = eng.incremental_vouchers("CMP")
    assert r["checkpoint"] == 103 and eng.quarantine.count_unresolved("vouchers") == 0


def test_upload_failure_goes_to_retry_queue_and_replays(tmp_path):
    src = FakeSource({date(2026, 4, 1): [_vp("A", 101)]})

    class Down(RecordingBackend):
        def sync_vouchers(self, *a, **k):
            raise E.BackendServerError("503")
    eng = _engine(tmp_path, src, Down())
    eng.masters = src.m
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=100)
    r = eng.incremental_vouchers("CMP")
    assert r["queued"] == 1 and eng.retry_queue.count_pending() == 1
    up = RecordingBackend()
    eng.backend = up
    with eng.retry_queue._connection() as c:  # make the queued batch due now
        c.execute("UPDATE retry_queue SET next_retry_at = '2000-01-01T00:00:00+00:00'")
        c.commit()
    eng.process_retry_queue()
    assert ("vouchers", ["A"]) in up.calls and eng.retry_queue.count_pending() == 0


def test_dry_run_backend_writes_payloads_and_uploads_nothing(tmp_path):
    be = DryRunBackend(tmp_path / "p")
    res = be.sync_vouchers("b1", "CMP", [_vp("A", 1)])
    assert res["status"] == "DRY_RUN" and res["total_received"] == 1
    files = list((tmp_path / "p").glob("*_vouchers.json"))
    assert len(files) == 1 and json.loads(files[0].read_text())["vouchers"][0]["guid"] == "A"
    assert be.get_pending_writeback_jobs() == []
