import xml.etree.ElementTree as ET
from unittest.mock import MagicMock

from tally_sync_agent.extractors.invoice_extractor import InvoiceExtractor
from tally_sync_agent.extractors.payment_extractor import PaymentExtractor


def _voucher_xml(root_tag: str, vouchers_xml: str) -> ET.Element:
    return ET.fromstring(f"<ENVELOPE><BODY><DATA><COLLECTION>{vouchers_xml}</COLLECTION></DATA></BODY></ENVELOPE>")


INVOICE_FIXTURE = """
<VOUCHER>
  <VOUCHERNUMBER>SGRG/UNO/11</VOUCHERNUMBER>
  <GUID>GUID-CANCELLED</GUID>
  <DATE>20260402</DATE>
  <PARTYLEDGERNAME></PARTYLEDGERNAME>
  <BASICBUYERNAME></BASICBUYERNAME>
  <VOUCHERTYPENAME>Oppo Unnao</VOUCHERTYPENAME>
  <ALTERID>40367</ALTERID>
  <AMOUNT></AMOUNT>
  <ISCANCELLED>Yes</ISCANCELLED>
</VOUCHER>
<VOUCHER>
  <VOUCHERNUMBER>SGRG/KNP/3624</VOUCHERNUMBER>
  <GUID>GUID-ACTIVE</GUID>
  <DATE>20261112</DATE>
  <PARTYLEDGERNAME>Aashi Mobile World</PARTYLEDGERNAME>
  <BASICBUYERNAME></BASICBUYERNAME>
  <VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>
  <ALTERID>40400</ALTERID>
  <AMOUNT>-91340.00</AMOUNT>
  <ISCANCELLED>No</ISCANCELLED>
</VOUCHER>
"""

PAYMENT_FIXTURE = """
<VOUCHER>
  <VOUCHERNUMBER>RCPT-99</VOUCHERNUMBER>
  <GUID>GUID-RCPT-CANCELLED</GUID>
  <DATE>20260402</DATE>
  <PARTYLEDGERNAME></PARTYLEDGERNAME>
  <VOUCHERTYPENAME>Receipt</VOUCHERTYPENAME>
  <ALTERID>50001</ALTERID>
  <AMOUNT></AMOUNT>
  <NARRATION></NARRATION>
  <ISCANCELLED>Yes</ISCANCELLED>
</VOUCHER>
<VOUCHER>
  <VOUCHERNUMBER>RCPT-100</VOUCHERNUMBER>
  <GUID>GUID-RCPT-ACTIVE</GUID>
  <DATE>20261112</DATE>
  <PARTYLEDGERNAME>Aashi Mobile World</PARTYLEDGERNAME>
  <VOUCHERTYPENAME>Receipt</VOUCHERTYPENAME>
  <ALTERID>50002</ALTERID>
  <AMOUNT>-5000.00</AMOUNT>
  <NARRATION></NARRATION>
  <ISCANCELLED>No</ISCANCELLED>
</VOUCHER>
"""


def test_invoice_extractor_excludes_cancelled_voucher():
    mock_tally = MagicMock()
    mock_tally.execute_tdl.return_value = _voucher_xml("VOUCHER", INVOICE_FIXTURE)

    extractor = InvoiceExtractor(mock_tally)
    results = extractor.extract_invoices(from_date="2026-04-01", to_date="2026-11-13")

    guids = [r["source_reference"] for r in results]
    assert "GUID-CANCELLED" not in guids
    assert "GUID-ACTIVE" in guids
    assert len(results) == 1


def test_invoice_extractor_still_extracts_active_voucher_correctly():
    mock_tally = MagicMock()
    mock_tally.execute_tdl.return_value = _voucher_xml("VOUCHER", INVOICE_FIXTURE)

    extractor = InvoiceExtractor(mock_tally)
    results = extractor.extract_invoices(from_date="2026-04-01", to_date="2026-11-13")

    active = next(r for r in results if r["source_reference"] == "GUID-ACTIVE")
    assert active["customer_name"] == "Aashi Mobile World"
    assert active["invoice_number"] == "SGRG/KNP/3624"
    assert active["amount"] == 91340.00


def test_payment_extractor_excludes_cancelled_voucher():
    mock_tally = MagicMock()
    mock_tally.execute_tdl.return_value = _voucher_xml("VOUCHER", PAYMENT_FIXTURE)

    extractor = PaymentExtractor(mock_tally)
    results = extractor.extract_payments(from_date="2026-04-01", to_date="2026-11-13")

    guids = [r["source_reference"] for r in results]
    assert "GUID-RCPT-CANCELLED" not in guids
    assert "GUID-RCPT-ACTIVE" in guids
    assert len(results) == 1


def test_payment_extractor_still_extracts_active_voucher_correctly():
    mock_tally = MagicMock()
    mock_tally.execute_tdl.return_value = _voucher_xml("VOUCHER", PAYMENT_FIXTURE)

    extractor = PaymentExtractor(mock_tally)
    results = extractor.extract_payments(from_date="2026-04-01", to_date="2026-11-13")

    active = next(r for r in results if r["source_reference"] == "GUID-RCPT-ACTIVE")
    assert active["customer_name"] == "Aashi Mobile World"
    assert active["amount"] == 5000.00


def test_invoice_extractor_query_string_also_excludes_cancelled_at_tally_side():
    """Belt-and-suspenders: the TDL formula sent to Tally itself must also exclude
    cancelled vouchers, not just the Python-side post-filter."""
    mock_tally = MagicMock()
    mock_tally.execute_tdl.return_value = _voucher_xml("VOUCHER", "")

    extractor = InvoiceExtractor(mock_tally)
    extractor.extract_invoices(from_date="2026-04-01", to_date="2026-11-13")

    sent_query = mock_tally.execute_tdl.call_args[0][0]
    assert "NOT $IsCancelled" in sent_query


def test_payment_extractor_query_string_also_excludes_cancelled_at_tally_side():
    mock_tally = MagicMock()
    mock_tally.execute_tdl.return_value = _voucher_xml("VOUCHER", "")

    extractor = PaymentExtractor(mock_tally)
    extractor.extract_payments(from_date="2026-04-01", to_date="2026-11-13")

    sent_query = mock_tally.execute_tdl.call_args[0][0]
    assert "NOT $IsCancelled" in sent_query
