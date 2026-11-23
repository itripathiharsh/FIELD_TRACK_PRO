import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, List, Optional

from tally_sync_agent.core.logger import logger
from tally_sync_agent.core.tally_client import TallyClient
from tally_sync_agent.extractors.brand_resolver import BrandResolver
from tally_sync_agent.extractors.customer_extractor import DMS_REGEX
from tally_sync_agent.extractors.invoice_extractor import _parse_tally_date

UTR_REGEX = re.compile(r"\b(utr[:\s\-\#]*([a-zA-Z0-9]{8,22}))\b", re.IGNORECASE)
CHEQUE_REGEX = re.compile(r"\b(chq|cheque)[:\s\-\#]*([0-9]{6})\b", re.IGNORECASE)


class PaymentExtractor:
    """
    Extracts Receipt vouchers from Tally within specified date ranges.
    Resolves customer, brand, payment method (CASH, CHEQUE, ONLINE), and allocations.
    """

    def __init__(self, tally_client: TallyClient):
        self.client = tally_client

    def extract_payments(
        self, from_date: str, to_date: str, min_alter_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Extracts receipt vouchers between from_date and to_date.
        """
        t_from = from_date.replace("-", "")
        t_to = to_date.replace("-", "")

        filter_clause = ""
        formula_clause = ""
        if min_alter_id and min_alter_id > 0:
            filter_clause = "<FILTER>AlterIdFilter</FILTER>"
            formula_clause = f'<SYSTEM TYPE="Formulae" NAME="AlterIdFilter">$$Number:$AlterId &gt; {min_alter_id}</SYSTEM>'

        query = f"""<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>ReceiptVouchersCol</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
        <SVFROMDATE>{t_from}</SVFROMDATE>
        <SVTODATE>{t_to}</SVTODATE>
      </STATICVARIABLES>
      <TDL>
        <TDLMESSAGE>
          <COLLECTION NAME="ReceiptVouchersCol">
            <TYPE>Voucher</TYPE>
            <FETCH>VoucherNumber, Date, PartyLedgerName, Guid, AlterId, VoucherTypeName, Amount, IsCancelled, AllLedgerEntries.List, AllLedgerEntries.BillAllocations.List</FETCH>
            <FILTER>IsReceiptVoucher</FILTER>
          </COLLECTION>
          <SYSTEM TYPE="Formulae" NAME="IsReceiptVoucher">($VoucherTypeName = "Receipt" OR $VoucherTypeName = "BANK RECEIPT" OR $$IsReceipt:$VoucherTypeName) AND NOT $IsCancelled</SYSTEM>
        </TDLMESSAGE>
      </TDL>
    </DESC>
  </BODY>
</ENVELOPE>"""

        logger.info(f"Extracting receipt vouchers from Tally ({from_date} to {to_date})...")
        root = self.client.execute_tdl(query)
        vouchers = root.findall(".//VOUCHER")
        logger.info(f"Retrieved {len(vouchers)} receipt vouchers from Tally.")

        extracted: List[Dict[str, Any]] = []
        for vch in vouchers:
            vch_num = (vch.findtext("VOUCHERNUMBER") or "").strip()

            is_cancelled = (vch.findtext("ISCANCELLED") or "No").strip().lower() == "yes"
            if is_cancelled:
                # Defense in depth: the Tally-side filter above already excludes these,
                # but a cancelled voucher has no party/ledger/amount by design.
                continue

            guid = (vch.findtext("GUID") or "").strip()
            raw_date = vch.findtext("DATE")
            iso_date = _parse_tally_date(raw_date) or datetime.now().strftime("%Y-%m-%d")
            party_name = (vch.findtext("PARTYLEDGERNAME") or "").strip()
            narration = (vch.findtext("NARRATION") or "").strip()

            alter_id_str = (vch.findtext("ALTERID") or "0").strip()
            try:
                alter_id = int(alter_id_str)
            except ValueError:
                alter_id = 0

            if min_alter_id and min_alter_id > 0 and alter_id <= min_alter_id:
                continue

            # Amount
            try:
                amount_val = abs(float(vch.findtext("AMOUNT") or "0"))
            except ValueError:
                amount_val = 0.0

            if amount_val == 0.0:
                for entry in vch.findall(".//LEDGERENTRIES.LIST") + vch.findall(".//ALLLEDGERENTRIES.LIST"):
                    try:
                        amt = abs(float(entry.findtext("AMOUNT") or "0"))
                        if amt > amount_val:
                            amount_val = amt
                    except ValueError:
                        pass

            # Detect Payment Method
            payment_method = "CASH"
            utr_ref = None
            cheque_no = None

            utr_match = UTR_REGEX.search(narration)
            if utr_match:
                payment_method = "ONLINE"
                utr_ref = utr_match.group(2)
            else:
                chq_match = CHEQUE_REGEX.search(narration)
                if chq_match:
                    payment_method = "CHEQUE"
                    cheque_no = chq_match.group(2)
                elif "neft" in narration.lower() or "rtgs" in narration.lower() or "upi" in narration.lower():
                    payment_method = "ONLINE"

            # Brand & DMS code
            dms_code = None
            dms_match = DMS_REGEX.search(party_name)
            if dms_match:
                dms_code = dms_match.group(1).upper()
            brand = BrandResolver.resolve(ledger_name=party_name, outlet_code=dms_code)

            # Brand allocations
            brand_allocations = []
            if brand and amount_val > 0:
                brand_allocations.append({
                    "brand": brand,
                    "allocated_amount": amount_val,
                })

            # Bill Allocations (<BILLALLOCATIONS.LIST>)
            bill_allocations = []
            for bill in vch.findall(".//BILLALLOCATIONS.LIST"):
                b_name = (bill.findtext("NAME") or "").strip()
                b_type = (bill.findtext("BILLTYPE") or "").strip()
                try:
                    b_amt = abs(float(bill.findtext("AMOUNT") or "0"))
                except ValueError:
                    b_amt = 0.0
                if b_name and b_amt > 0:
                    bill_allocations.append({
                        "bill_name": b_name,
                        "bill_type": b_type,
                        "amount": b_amt,
                    })

            extracted.append({
                "source_reference": guid or f"TALLY_RCPT_{vch_num}_{iso_date}",
                "receipt_number": vch_num or f"RCPT-{iso_date}",
                "customer_name": party_name,
                "outlet_code": dms_code,
                "payment_date": iso_date,
                "amount": amount_val,
                "payment_method": payment_method,
                "utr_reference": utr_ref,
                "cheque_number": cheque_no,
                "notes": narration,
                "brand_allocations": brand_allocations,
                "bill_allocations": bill_allocations,
                "alter_id": alter_id,
            })

        return extracted
