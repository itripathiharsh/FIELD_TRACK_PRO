"""
Stage 3 extraction/mapping: real due dates and bill names, bill-wise receipt
allocations reaching the payload, ledger mobile/email/closing balance, backdated
vouchers in incremental cycles, the checkpoint-independent full extraction, and
the masked ledger inspection.
"""
import json
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock

import pytest

from tally_sync_agent.config.settings import settings
from tally_sync_agent.engine import full_extraction
from tally_sync_agent.engine.ledger_inspection import mask, summarize_ledgers
from tally_sync_agent.engine.sync_engine import SyncEngine
from tally_sync_agent.extractors.customer_extractor import CustomerExtractor
from tally_sync_agent.extractors.invoice_extractor import InvoiceExtractor, parse_due_date
from tally_sync_agent.extractors.payment_extractor import PaymentExtractor
from tally_sync_agent.transformers.normalizer import Normalizer


def _env(inner: str) -> ET.Element:
    return ET.fromstring(f"<ENVELOPE><BODY><DATA><COLLECTION>{inner}</COLLECTION></DATA></BODY></ENVELOPE>")


SALES = """
<VOUCHER>
  <VOUCHERNUMBER>SGRG/KNP/1</VOUCHERNUMBER><GUID>G-INV-1</GUID><DATE>20260501</DATE>
  <PARTYLEDGERNAME>Aashi Mobile World</PARTYLEDGERNAME><VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>
  <ALTERID>100</ALTERID><AMOUNT>-11800.00</AMOUNT><ISCANCELLED>No</ISCANCELLED>
  <ALLLEDGERENTRIES.LIST>
    <LEDGERNAME>USHA SALES</LEDGERNAME><AMOUNT>10000.00</AMOUNT>
  </ALLLEDGERENTRIES.LIST>
  <ALLLEDGERENTRIES.LIST>
    <LEDGERNAME>Aashi Mobile World</LEDGERNAME><AMOUNT>-11800.00</AMOUNT>
    <BILLALLOCATIONS.LIST>
      <NAME>KNP-1</NAME><BILLTYPE>New Ref</BILLTYPE><BILLCREDITPERIOD>30 Days</BILLCREDITPERIOD><AMOUNT>-11800.00</AMOUNT>
    </BILLALLOCATIONS.LIST>
  </ALLLEDGERENTRIES.LIST>
</VOUCHER>
<VOUCHER>
  <VOUCHERNUMBER>SGRG/KNP/2</VOUCHERNUMBER><GUID>G-INV-2</GUID><DATE>20260502</DATE>
  <PARTYLEDGERNAME>Other Store</PARTYLEDGERNAME><VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>
  <ALTERID>101</ALTERID><AMOUNT>-500.00</AMOUNT><ISCANCELLED>No</ISCANCELLED>
</VOUCHER>
"""

RECEIPT = """
<VOUCHER>
  <VOUCHERNUMBER>R-1</VOUCHERNUMBER><GUID>G-R-1</GUID><DATE>20260510</DATE>
  <PARTYLEDGERNAME>Aashi Mobile World</PARTYLEDGERNAME><VOUCHERTYPENAME>Receipt</VOUCHERTYPENAME>
  <ALTERID>200</ALTERID><AMOUNT>-7000.00</AMOUNT><NARRATION>NEFT</NARRATION><ISCANCELLED>No</ISCANCELLED>
  <ALLLEDGERENTRIES.LIST>
    <LEDGERNAME>Aashi Mobile World</LEDGERNAME><AMOUNT>7000.00</AMOUNT>
    <BILLALLOCATIONS.LIST><NAME>KNP-1</NAME><BILLTYPE>Agst Ref</BILLTYPE><AMOUNT>5000.00</AMOUNT></BILLALLOCATIONS.LIST>
    <BILLALLOCATIONS.LIST><NAME>OLD-2025-77</NAME><BILLTYPE>Agst Ref</BILLTYPE><AMOUNT>2000.00</AMOUNT></BILLALLOCATIONS.LIST>
  </ALLLEDGERENTRIES.LIST>
  <ALLLEDGERENTRIES.LIST><LEDGERNAME>HDFC BANK</LEDGERNAME><AMOUNT>-7000.00</AMOUNT></ALLLEDGERENTRIES.LIST>
</VOUCHER>
"""

LEDGERS = """
<LEDGER NAME="Aashi Mobile World">
  <NAME>Aashi Mobile World</NAME><PARENT>Sundry Debtors - Philips</PARENT><GUID>G-LED-1</GUID><ALTERID>9</ALTERID>
  <LEDGERMOBILE>9876543210</LEDGERMOBILE><EMAIL>shop@example.com</EMAIL><CLOSINGBALANCE>-4800.00</CLOSINGBALANCE>
  <OPENINGBALANCE>-2000.00</OPENINGBALANCE>
  <LEDMAILINGDETAILS.LIST><ADDRESS.LIST><ADDRESS>Kidwai Nagar</ADDRESS><ADDRESS>Kanpur</ADDRESS></ADDRESS.LIST>
    <PINCODE>208011</PINCODE><STATE>Uttar Pradesh</STATE></LEDMAILINGDETAILS.LIST>
  <LEDGSTREGDETAILS.LIST><GSTIN>09ABCDE1234F1Z5</GSTIN></LEDGSTREGDETAILS.LIST>
</LEDGER>
"""


def _tally(xml):
    t = MagicMock()
    t.execute_tdl.return_value = _env(xml)
    return t


@pytest.mark.parametrize("raw,expected", [
    ("30 Days", "2026-05-31"), ("45", "2026-06-15"), ("1 Day", "2026-05-02"),
    ("20260515", "2026-05-15"), ("2026-05-20", "2026-05-20"), ("5-Jun-2026", "2026-06-05"),
    ("", None), (None, None), ("as agreed", None),
])
def test_parse_due_date(raw, expected):
    assert parse_due_date(raw, "2026-05-01") == expected


def test_invoice_due_date_and_bill_name_from_party_bill_allocation_no_default():
    out = {i["invoice_number"]: i for i in InvoiceExtractor(_tally(SALES)).extract_invoices("2026-04-01", "2026-11-15")}
    assert out["SGRG/KNP/1"]["due_date"] == "2026-05-31"
    assert out["SGRG/KNP/1"]["bill_name"] == "KNP-1"
    # No bill allocation in Tally: due date stays unknown instead of an invented +21 days.
    assert out["SGRG/KNP/2"]["due_date"] is None and out["SGRG/KNP/2"]["bill_name"] is None
    norm = Normalizer.normalize_invoice(out["SGRG/KNP/1"])
    assert norm["bill_name"] == "KNP-1" and norm["due_date"] == "2026-05-31"


def test_invoice_query_fetches_bill_allocations_and_filters_alter_id_in_tally():
    t = _tally("")
    InvoiceExtractor(t).extract_invoices("2026-04-01", "2026-11-15", min_alter_id=500)
    q = t.execute_tdl.call_args[0][0]
    assert "AllLedgerEntries.BillAllocations.List" in q
    assert "AlterIdFilter" in q and "&gt; 500" in q
    InvoiceExtractor(t).extract_invoices("2026-04-01", "2026-11-15", min_alter_id=None)
    assert "AlterIdFilter" not in t.execute_tdl.call_args[0][0]


def test_receipt_bill_allocations_reach_the_backend_payload():
    raw = PaymentExtractor(_tally(RECEIPT)).extract_payments("2026-04-01", "2026-11-15")
    norm = Normalizer.normalize_payment(raw[0])
    assert norm["bill_allocations"] == [
        {"bill_name": "KNP-1", "bill_type": "Agst Ref", "amount": 5000.0},
        {"bill_name": "OLD-2025-77", "bill_type": "Agst Ref", "amount": 2000.0},
    ]


def test_customer_mobile_email_closing_balance_and_nested_fields():
    raw = CustomerExtractor(_tally(LEDGERS)).extract_customers()
    c = Normalizer.normalize_customer(raw[0])
    assert c["source_reference"] == "G-LED-1"
    assert c["mobile"] == "9876543210" and c["email"] == "shop@example.com"
    assert c["closing_balance"] == -4800.0
    assert c["gst_number"] == "09ABCDE1234F1Z5"
    assert c["pincode"] == "208011" and c["state"] == "Uttar Pradesh"
    assert "Kidwai Nagar" in c["address"]


def _engine():
    tally = MagicMock()
    tally.get_company_info.return_value = {"name": "SGRG", "guid": "CO-1"}
    backend = MagicMock()
    for fn in ("sync_customers", "sync_invoices", "sync_payments"):
        getattr(backend, fn).return_value = {"created_count": 1, "updated_count": 0, "failed_count": 0}
    checkpoints, retry, quarantine = MagicMock(), MagicMock(), MagicMock()
    eng = SyncEngine(tally_client=tally, backend_client=backend, checkpoint_manager=checkpoints,
                     retry_queue=retry, quarantine_store=quarantine)
    eng.cust_extractor = MagicMock(extract_customers=MagicMock(return_value=CustomerExtractor(_tally(LEDGERS)).extract_customers()))
    eng.inv_extractor = MagicMock(extract_invoices=MagicMock(return_value=InvoiceExtractor(_tally(SALES)).extract_invoices("a", "b")))
    eng.pmt_extractor = MagicMock(extract_payments=MagicMock(return_value=PaymentExtractor(_tally(RECEIPT)).extract_payments("a", "b")))
    return eng, backend, checkpoints, retry, quarantine


def test_full_extraction_dry_run_never_touches_checkpoints_or_backend(tmp_path):
    eng, backend, checkpoints, retry, quarantine = _engine()
    report = full_extraction.run_full_extraction(eng, upload=False, report_dir=tmp_path)
    assert report["status"] == "DRY_RUN_COMPLETE" and report["checkpoints_touched"] is False
    assert not checkpoints.method_calls and not retry.method_calls and not quarantine.method_calls
    assert not backend.sync_customers.called and not backend.sync_invoices.called and not backend.sync_payments.called
    eng.inv_extractor.extract_invoices.assert_called_once()
    assert eng.inv_extractor.extract_invoices.call_args.kwargs["min_alter_id"] is None
    assert eng.inv_extractor.extract_invoices.call_args.kwargs["from_date"] == settings.sync_from_date
    assert report["invoices"]["amount_sum"] == 12300.0
    assert report["invoices"]["with_due_date_from_tally"] == 1 and report["invoices"]["without_due_date"] == 1
    assert report["payments"]["bill_allocated_sum"] == 7000.0 and report["payments"]["with_bill_allocations"] == 1
    assert report["customers"]["with_mobile"] == 1 and report["customers"]["closing_balance_negative_count"] == 1
    assert report["customers"]["opening_balance_sum_signed"] == -2000.0
    mv = report["debtor_movement_check"]
    assert mv["expected_closing_if_debit_negative"] == -7300.0 and mv["unexplained_difference"] == 2500.0
    saved = json.loads(open(report["report_path"], encoding="utf-8").read())
    assert "Aashi" not in json.dumps(saved), "report holds aggregates only, no party names"
    manifest = json.loads(open(report["guid_manifest_path"], encoding="utf-8").read())
    assert manifest["invoices"] == ["G-INV-1", "G-INV-2"] and manifest["payments"] == ["G-R-1"]
    assert manifest["customers"] == ["G-LED-1"] and "Aashi" not in json.dumps(manifest)


def test_full_extraction_upload_order_and_still_no_checkpoints(tmp_path):
    eng, backend, checkpoints, retry, quarantine = _engine()
    order = []
    for fn in ("sync_customers", "sync_invoices", "sync_payments"):
        getattr(backend, fn).side_effect = (lambda f: lambda *a: order.append(f) or {"created_count": len(a[2]), "updated_count": 0})(fn)
    report = full_extraction.run_full_extraction(eng, upload=True, report_dir=tmp_path)
    assert report["status"] == "UPLOADED"
    assert order == ["sync_customers", "sync_invoices", "sync_payments"]
    assert not checkpoints.method_calls and not retry.method_calls


def test_full_extraction_reports_failed_batches_without_queueing(tmp_path):
    eng, backend, checkpoints, retry, _ = _engine()
    backend.sync_invoices.side_effect = RuntimeError("backend down")
    report = full_extraction.run_full_extraction(eng, upload=True, report_dir=tmp_path)
    assert report["status"] == "UPLOADED_WITH_FAILURES"
    assert report["upload"]["invoices"]["failed_batches"] == 1
    assert not retry.method_calls


def test_incremental_cycle_looks_back_to_sync_start_for_backdated_vouchers():
    eng, *_ = _engine()
    eng.checkpoints.get_checkpoint.return_value = {"last_sync_date": "2026-11-14", "last_alter_id": 150}
    eng.quarantine.list_unresolved.return_value = []
    eng.run_sync(is_initial=False)
    kw = eng.inv_extractor.extract_invoices.call_args.kwargs
    assert kw["from_date"] == settings.sync_from_date and kw["min_alter_id"] == 150
    assert eng.pmt_extractor.extract_payments.call_args.kwargs["from_date"] == settings.sync_from_date


def test_ledger_inspection_masks_values_and_counts_fields():
    assert mask("UPDD640001") == "AAAA999999"
    assert mask("-4800.00") == "-9999.99"
    report = summarize_ledgers(_env(LEDGERS + LEDGERS.replace("<EMAIL>shop@example.com</EMAIL>", "")))
    assert report["ledger_count"] == 2
    assert report["fields"]["EMAIL"]["ledgers_with_value"] == 1
    assert report["fields"]["LEDGERMOBILE"]["ledgers_with_value"] == 2
    assert report["fields"]["CLOSINGBALANCE"]["top_shapes"][0] == {"shape": "-9999.99", "count": 2}
    assert "Aashi" not in json.dumps(report)
