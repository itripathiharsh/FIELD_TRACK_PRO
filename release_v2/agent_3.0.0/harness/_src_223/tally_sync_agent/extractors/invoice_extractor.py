import re
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional

from tally_sync_agent.core.logger import logger
from tally_sync_agent.core.tally_client import TallyClient
from tally_sync_agent.extractors.brand_resolver import BrandResolver
from tally_sync_agent.extractors.customer_extractor import DMS_REGEX


def _parse_tally_date(date_str: Optional[str]) -> Optional[str]:
    """Parses YYYYMMDD or YYYY-MM-DD into ISO format YYYY-MM-DD."""
    if not date_str:
        return None
    cleaned = date_str.strip().replace("-", "")
    if len(cleaned) == 8 and cleaned.isdigit():
        try:
            return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:8]}"
        except Exception:
            pass
    return date_str.strip()


_CREDIT_DAYS_RE = re.compile(r"^\s*(\d{1,4})\s*(?:days?)?\s*$", re.IGNORECASE)


def parse_due_date(raw: Optional[str], invoice_iso: Optional[str]) -> Optional[str]:
    """
    Due date from a Tally bill's credit period, ISO, or None when Tally gives none
    or a form not recognised. Tally lets the credit period be entered as a number of
    days ("30", "30 Days") or as a date; both are handled. Nothing is defaulted:
    an unknown due date stays unknown (None) rather than being invented.
    """
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    m = _CREDIT_DAYS_RE.match(text)
    if m:
        if not invoice_iso:
            return None
        try:
            return (datetime.strptime(invoice_iso, "%Y-%m-%d").date() + timedelta(days=int(m.group(1)))).isoformat()
        except ValueError:
            return None
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%d-%b-%Y", "%d-%b-%y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _party_bill_allocation(vch: ET.Element, party_name: str) -> Optional[ET.Element]:
    """The party ledger entry's first bill allocation (the bill this invoice raises)."""
    entries = vch.findall(".//ALLLEDGERENTRIES.LIST") + vch.findall(".//LEDGERENTRIES.LIST")
    party_lower = party_name.strip().lower()
    for entry in entries:
        if (entry.findtext("LEDGERNAME") or "").strip().lower() == party_lower:
            alloc = entry.find("BILLALLOCATIONS.LIST")
            if alloc is not None:
                return alloc
    return None


class InvoiceExtractor:
    """
    Extracts Sales Vouchers from Tally within specified date ranges.
    Uses indexed TDL queries to prevent full-database scans.
    """

    def __init__(self, tally_client: TallyClient):
        self.client = tally_client

    def extract_invoices(
        self, from_date: str, to_date: str, min_alter_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Extracts sales vouchers between from_date and to_date (ISO YYYY-MM-DD or YYYYMMDD).
        """
        # Format for Tally Static Variables: YYYYMMDD
        t_from = from_date.replace("-", "")
        t_to = to_date.replace("-", "")

        alter_formula = ""
        filter_clause = "<FILTER>IsSalesVoucher</FILTER>"
        if min_alter_id and min_alter_id > 0:
            filter_clause += "<FILTER>AlterIdFilter</FILTER>"
            alter_formula = f'<SYSTEM TYPE="Formulae" NAME="AlterIdFilter">$$Number:$AlterId &gt; {min_alter_id}</SYSTEM>'

        query = f"""<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>SalesVouchersCol</ID>
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
          <COLLECTION NAME="SalesVouchersCol">
            <TYPE>Voucher</TYPE>
            <FETCH>VoucherNumber, Date, PartyLedgerName, BasicBuyerName, Guid, AlterId, VoucherTypeName, Amount, IsCancelled, AllLedgerEntries.List, AllLedgerEntries.BillAllocations.List</FETCH>
            {filter_clause}
          </COLLECTION>
          <SYSTEM TYPE="Formulae" NAME="IsSalesVoucher">$$IsSales:$VoucherTypeName AND NOT $IsCancelled</SYSTEM>
          {alter_formula}
        </TDLMESSAGE>
      </TDL>
    </DESC>
  </BODY>
</ENVELOPE>"""

        logger.info(f"Extracting sales vouchers from Tally ({from_date} to {to_date})...")
        root = self.client.execute_tdl(query)
        vouchers = root.findall(".//VOUCHER")
        logger.info(f"Retrieved {len(vouchers)} sales vouchers from Tally.")

        extracted: List[Dict[str, Any]] = []
        for vch in vouchers:
            vch_num = (vch.findtext("VOUCHERNUMBER") or "").strip()
            if not vch_num:
                continue

            is_cancelled = (vch.findtext("ISCANCELLED") or "No").strip().lower() == "yes"
            if is_cancelled:
                # Defense in depth: the Tally-side filter above already excludes these,
                # but a cancelled voucher has no party/ledger/amount by design, so a
                # second check here means a filter change elsewhere can never
                # reintroduce "missing customer_name" noise from cancelled vouchers.
                continue

            guid = (vch.findtext("GUID") or "").strip()
            raw_date = vch.findtext("DATE")
            iso_date = _parse_tally_date(raw_date) or datetime.now().strftime("%Y-%m-%d")

            party_name = (
                vch.findtext("PARTYLEDGERNAME")
                or vch.findtext("BASICBUYERNAME")
                or ""
            ).strip()

            vch_type = (vch.findtext("VOUCHERTYPENAME") or "Sales").strip()
            alter_id_str = (vch.findtext("ALTERID") or "0").strip()
            try:
                alter_id = int(alter_id_str)
            except ValueError:
                alter_id = 0

            if min_alter_id and min_alter_id > 0 and alter_id <= min_alter_id:
                continue

            # Compute net amount
            # In Tally sales vouchers, Amount can be negative or positive depending on entry convention
            raw_amt = vch.findtext("AMOUNT") or "0"
            try:
                amount_val = abs(float(raw_amt))
            except ValueError:
                amount_val = 0.0

            # If voucher level amount is 0, sum from ledger entries
            if amount_val == 0.0:
                for entry in vch.findall(".//LEDGERENTRIES.LIST") + vch.findall(".//ALLLEDGERENTRIES.LIST"):
                    try:
                        amt = abs(float(entry.findtext("AMOUNT") or "0"))
                        if amt > amount_val:
                            amount_val = amt
                    except ValueError:
                        pass

            # The bill this invoice raises (party entry's bill allocation): its name is
            # what receipts reference ("Agst Ref"); its credit period gives the due date.
            bill_alloc = _party_bill_allocation(vch, party_name) if party_name else None
            bill_name = None
            due_date_iso = None
            if bill_alloc is not None:
                bill_name = (bill_alloc.findtext("NAME") or "").strip() or None
                due_date_iso = parse_due_date(bill_alloc.findtext("BILLCREDITPERIOD"), iso_date)

            # Brand and DMS code
            dms_code = None
            dms_match = DMS_REGEX.search(party_name)
            if dms_match:
                dms_code = dms_match.group(1).upper()
            brand = BrandResolver.resolve(ledger_name=party_name, outlet_code=dms_code)

            # Bill-wise closing balance if provided by Tally; otherwise None for dynamic computation
            closing_balance = None
            if bill_alloc is not None:
                raw_cb = bill_alloc.findtext("CLOSINGBALANCE")
                if raw_cb:
                    try:
                        closing_balance = abs(float(raw_cb))
                    except ValueError:
                        pass

            extracted.append({
                "source_reference": guid or f"TALLY_INV_{vch_num}",
                "invoice_number": vch_num,
                "customer_name": party_name,
                "outlet_code": dms_code,
                "invoice_date": iso_date,
                "due_date": due_date_iso,
                "amount": amount_val,
                "brand": brand,
                "voucher_type": vch_type,
                "imported_outstanding_amount": closing_balance,
                "bill_name": bill_name,
                "alter_id": alter_id,
            })

        return extracted
