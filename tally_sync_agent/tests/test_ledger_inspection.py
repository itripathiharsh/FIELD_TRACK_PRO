"""Read-only ledger inspection tool (kept from the removed v1 stage-3 test module in 3.0)."""
import json
import xml.etree.ElementTree as ET

from tally_sync_agent.engine.ledger_inspection import mask, summarize_ledgers


def _env(inner: str) -> ET.Element:
    return ET.fromstring(f"<ENVELOPE><BODY><DATA><COLLECTION>{inner}</COLLECTION></DATA></BODY></ENVELOPE>")


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


def test_ledger_inspection_masks_values_and_counts_fields():
    assert mask("UPDD640001") == "AAAA999999"
    assert mask("-4800.00") == "-9999.99"
    report = summarize_ledgers(_env(LEDGERS + LEDGERS.replace("<EMAIL>shop@example.com</EMAIL>", "")))
    assert report["ledger_count"] == 2
    assert report["fields"]["EMAIL"]["ledgers_with_value"] == 1
    assert report["fields"]["LEDGERMOBILE"]["ledgers_with_value"] == 2
    assert report["fields"]["CLOSINGBALANCE"]["top_shapes"][0] == {"shape": "-9999.99", "count": 2}
    assert "Aashi" not in json.dumps(report)
