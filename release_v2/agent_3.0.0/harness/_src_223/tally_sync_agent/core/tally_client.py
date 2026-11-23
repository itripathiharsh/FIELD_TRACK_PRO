import dataclasses
import re
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape

from tally_sync_agent.config.settings import settings
from tally_sync_agent.core.logger import logger

# Regex to strip invalid XML control characters that Tally sometimes emits
ILLEGAL_XML_CHARS = re.compile(
    r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]|&#(?:[0-8]|1[124-9]|2[0-9]|3[01]);"
)


class TallyConnectionError(Exception):
    """Raised when communication with TallyPrime fails."""
    pass


class TallyImportError(Exception):
    """Raised when Tally rejects an import operation."""
    pass


@dataclasses.dataclass
class TallyImportResult:
    success: bool
    created_count: int = 0
    altered_count: int = 0
    master_id: Optional[str] = None
    last_vch_id: Optional[str] = None
    guid: Optional[str] = None
    voucher_number: Optional[str] = None
    alter_id: Optional[int] = None
    error_message: Optional[str] = None
    is_retryable: bool = True



class TallyClient:
    """
    Communicates with the local TallyPrime instance via XML over HTTP (port 9000).
    Provides export (TDL) and import (Voucher Write-Back) functionality.
    """

    # Verified Bank & Cash ledgers in SGRG SERVICES (OPC) PRIVATE LIMITED
    DEFAULT_CASH_LEDGER = "Cash"
    DEFAULT_BANK_LEDGER = "HDFC BANK A/c No. 50200093755673"
    KNOWN_BANK_LEDGERS = [
        "HDFC BANK A/c No. 50200093755673",
        "UCO BANK OD A/C No. 25540510002018",
        "UCO C/C A/C NO. 25540510001981",
        "SBi C/C A/c 44881896899",
    ]

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[int] = None):
        self.base_url = base_url or settings.tally_url
        self.timeout = timeout or settings.tally_timeout_seconds

    def is_reachable(self) -> bool:
        """Fast non-blocking socket probe to verify if TallyPrime is listening on port 9000."""
        import socket
        from urllib.parse import urlparse
        try:
            parsed = urlparse(self.base_url)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 9000
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                return s.connect_ex((host, port)) == 0
        except Exception:
            return False

    def _clean_xml(self, raw: str) -> str:
        """Strip control characters and fix unbound namespace prefixes (e.g. UDF:xxx)."""
        cleaned = ILLEGAL_XML_CHARS.sub("", raw)
        return re.sub(r'<(/?)(\w+):', r'<\1\2_', cleaned)

    def send_xml(self, xml_payload: str) -> str:
        """
        Sends raw XML to TallyPrime and returns the response string.
        """
        cleaned_payload = xml_payload.strip()
        data = cleaned_payload.encode("utf-8")
        req = urllib.request.Request(
            self.base_url,
            data=data,
            headers={
                "Content-Type": "text/xml;charset=utf-8",
                "Connection": "close",
                "Content-Length": str(len(data)),
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_bytes = resp.read()
                raw_text = resp_bytes.decode("utf-8", errors="replace")
                return self._clean_xml(raw_text)
        except urllib.error.URLError as ex:
            logger.warning(f"Tally connection failed: {ex}")
            raise TallyConnectionError(f"Could not connect to Tally at {self.base_url}: {ex}") from ex
        except Exception as ex:
            logger.warning(f"Unexpected error communicating with Tally: {ex}")
            raise TallyConnectionError(f"Tally query failed: {ex}") from ex

    def execute_tdl(self, xml_payload: str) -> ET.Element:
        """
        Sends XML request and parses response into an XML ElementTree root.
        """
        response_text = self.send_xml(xml_payload)
        try:
            return ET.fromstring(response_text)
        except ET.ParseError as pe:
            logger.error(f"Failed to parse XML response from Tally: {pe}")
            # Try once more with aggressive character stripping
            safe_text = re.sub(r"[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD]", "", response_text)
            return ET.fromstring(safe_text)

    def list_companies(self) -> List[Dict[str, str]]:
        """Every company OBJECT loaded in Tally. Scalar <COMPANY>8</COMPANY> count fields (inside
        <CMPINFO>) are not companies and are skipped (the 2.1.0 'blank company', R9)."""
        from tally_sync_agent.extractors import tally_xml as tx
        root = self.execute_tdl(tx.company_request())
        out = []
        for cmp in root.iter("COMPANY"):
            if not len(cmp):
                continue
            name = (cmp.findtext("NAME") or cmp.attrib.get("NAME", "")).strip()
            if not name:
                continue
            out.append({
                "name": name,
                "guid": (cmp.findtext("GUID") or "").strip(),
                "starting_date": (cmp.findtext("STARTINGDATE") or "").strip(),
                "ending_date": (cmp.findtext("ENDINGDATE") or "").strip(),
                "books_from": (cmp.findtext("BOOKSFROM") or "").strip(),
            })
        return out

    def get_company_info(self) -> Optional[Dict[str, Any]]:
        """The company to sync, selected BY GUID (2.2.0, R9). Never guesses:

          * EXPECTED_COMPANY_GUID set   -> that company, or {"error": "WRONG_COMPANY", ...} if not loaded
          * not set, exactly one loaded -> that company
          * more than one loaded        -> {"error": "MULTIPLE_COMPANIES", ...} (unscoped master lists
                                           could otherwise come from another company)
          * none loaded                 -> None
        No GUID is ever made up (2.1.0 fell back to a hard-coded GUID)."""
        try:
            companies = self.list_companies()
        except TallyConnectionError:
            raise
        except Exception as ex:
            logger.warning(f"Failed to query the loaded companies: {ex}")
            return None
        if not companies:
            return None
        names = [c["name"] for c in companies]
        if len(companies) > 1:
            return {"error": "MULTIPLE_COMPANIES", "name": None, "guid": None, "companies": names}
        expected = (settings.expected_company_guid or "").strip()
        c = companies[0]
        if expected and c["guid"] != expected:
            return {"error": "WRONG_COMPANY", "name": c["name"], "guid": c["guid"] or None, "companies": names}
        if not c["guid"]:
            return {"error": "NO_COMPANY_GUID", "name": c["name"], "guid": None, "companies": names}
        return {**c, "companies": names}

    def resolve_bank_cash_ledger(
        self, payment_method: str, cheque_bank_name: Optional[str] = None
    ) -> str:
        """
        Resolves the appropriate bank or cash ledger name based on payment details.
        """
        method = (payment_method or "CASH").upper()
        if method == "CASH":
            return self.DEFAULT_CASH_LEDGER

        if cheque_bank_name:
            c_low = cheque_bank_name.lower()
            for known in self.KNOWN_BANK_LEDGERS:
                k_low = known.lower()
                if "hdfc" in c_low and "hdfc" in k_low:
                    return known
                if "uco" in c_low and "uco" in k_low:
                    return known
                if "sbi" in c_low and "sbi" in k_low:
                    return known

        return self.DEFAULT_BANK_LEDGER

    def build_receipt_xml(
        self, job_data: Dict[str, Any], company_name: Optional[str] = None
    ) -> str:
        """
        Generates standard Tally Import XML for a Receipt voucher.
        Guarantees:
        - Exact party and account ledger resolution
        - Correct debit / credit signs
        - Stable remote ID: ft_pmt_{payment_id}
        - Stable narration: FT:{payment_id} | ...
        - Bill allocations if invoice provided
        """
        payment_id = job_data.get("payment_id", "")
        customer_name = job_data.get("customer_name", "").strip()
        employee_name = (job_data.get("employee_name") or "").strip()
        amount = abs(float(job_data.get("amount", 0.0)))
        payment_date = job_data.get("payment_date", "").replace("-", "")
        payment_method = (job_data.get("payment_method", "CASH") or "CASH").upper()
        cheque_bank = job_data.get("cheque_bank_name")
        invoice_number = job_data.get("invoice_number")
        notes = job_data.get("notes", "").strip()
        utr_ref = (job_data.get("utr_reference") or "").strip()
        chq_num = (job_data.get("cheque_number") or "").strip()

        bank_cash_ledger = self.resolve_bank_cash_ledger(payment_method, cheque_bank)

        # Build narration following SGRG Tally convention:
        # CASH:   "Being Cash Rec. By {employee_name} | FT:{payment_id} | {notes}"
        # ONLINE: "Being Rec. By {employee_name} | UTR:{utr_reference} | FT:{payment_id} | {notes}"
        # CHEQUE: "Being Rec. By {employee_name} | CHQ:{cheque_number} | FT:{payment_id} | {notes}"
        narr_tokens = []
        if payment_method == "CASH":
            prefix = f"Being Cash Rec. By {employee_name}" if employee_name else "Being Cash Rec."
            narr_tokens.append(prefix)
            narr_tokens.append(f"FT:{payment_id}")
            if notes:
                narr_tokens.append(notes)
        elif payment_method == "CHEQUE":
            prefix = f"Being Rec. By {employee_name}" if employee_name else "Being Rec."
            narr_tokens.append(prefix)
            if chq_num:
                narr_tokens.append(f"CHQ:{chq_num}")
            narr_tokens.append(f"FT:{payment_id}")
            if notes:
                narr_tokens.append(notes)
        else:
            # ONLINE / Bank Transfer / UPI
            prefix = f"Being Rec. By {employee_name}" if employee_name else "Being Rec."
            narr_tokens.append(prefix)
            if utr_ref:
                narr_tokens.append(f"UTR:{utr_ref}")
            narr_tokens.append(f"FT:{payment_id}")
            if notes:
                narr_tokens.append(notes)

        narration = " | ".join(narr_tokens)

        remote_id = f"ft_pmt_{payment_id}"

        # Bill allocations
        if invoice_number:
            bill_alloc_xml = f"""      <BILLALLOCATIONS.LIST>
        <NAME>{escape(invoice_number)}</NAME>
        <BILLTYPE>Agst Ref</BILLTYPE>
        <AMOUNT>{amount:.2f}</AMOUNT>
      </BILLALLOCATIONS.LIST>"""
        else:
            bill_alloc_xml = f"""      <BILLALLOCATIONS.LIST>
        <NAME>On Account</NAME>
        <BILLTYPE>On Account</BILLTYPE>
        <AMOUNT>{amount:.2f}</AMOUNT>
      </BILLALLOCATIONS.LIST>"""

        target_company = company_name or "SGRG SERVICES (OPC) PRIVATE LIMITED"

        return f"""<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Import Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <IMPORTDATA>
      <REQUESTDESC>
        <REPORTNAME>Vouchers</REPORTNAME>
        <STATICVARIABLES>
          <SVCURRENTCOMPANY>{escape(target_company)}</SVCURRENTCOMPANY>
        </STATICVARIABLES>
      </REQUESTDESC>
      <REQUESTDATA>
        <TALLYMESSAGE xmlns:UDF="TallyUDF">
          <VOUCHER DATE="{payment_date}" REMOTEID="{escape(remote_id)}" VCHTYPE="Receipt" ACTION="Create" OBJVIEW="Accounting Voucher View">
            <DATE>{payment_date}</DATE>
            <EFFECTIVEDATE>{payment_date}</EFFECTIVEDATE>
            <VOUCHERTYPENAME>Receipt</VOUCHERTYPENAME>
            <PARTYLEDGERNAME>{escape(customer_name)}</PARTYLEDGERNAME>
            <NARRATION>{escape(narration)}</NARRATION>
            <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
            <AMOUNT>{amount:.2f}</AMOUNT>
            <!-- Party Ledger Entry (Credit) -->
            <ALLLEDGERENTRIES.LIST>
              <LEDGERNAME>{escape(customer_name)}</LEDGERNAME>
              <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
              <AMOUNT>{amount:.2f}</AMOUNT>
{bill_alloc_xml}
            </ALLLEDGERENTRIES.LIST>
            <!-- Cash/Bank Ledger Entry (Debit) -->
            <ALLLEDGERENTRIES.LIST>
              <LEDGERNAME>{escape(bank_cash_ledger)}</LEDGERNAME>
              <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
              <AMOUNT>-{amount:.2f}</AMOUNT>
            </ALLLEDGERENTRIES.LIST>
          </VOUCHER>
        </TALLYMESSAGE>
      </REQUESTDATA>
    </IMPORTDATA>
  </BODY>
</ENVELOPE>"""

    def parse_import_response(self, response_xml: str) -> TallyImportResult:
        """
        Parses Tally import response XML.
        Validates created/altered counts and line errors.
        """
        try:
            root = ET.fromstring(response_xml)
        except ET.ParseError as pe:
            logger.error(f"Failed to parse Tally import response: {pe}")
            return TallyImportResult(
                success=False,
                error_message=f"Malformed XML response from Tally: {pe}",
                is_retryable=True,
            )

        # Check for errors/line errors
        errors_str = root.findtext(".//ERRORS") or "0"
        exceptions_str = root.findtext(".//EXCEPTIONS") or "0"
        created_str = root.findtext(".//CREATED") or "0"
        altered_str = root.findtext(".//ALTERED") or "0"
        last_vch_id = root.findtext(".//LASTVCHID") or "0"

        line_errors = [
            node.text.strip()
            for node in root.findall(".//LINEERROR")
            if node.text and node.text.strip()
        ]

        try:
            errors_count = int(errors_str)
            exceptions_count = int(exceptions_str)
            created_count = int(created_str)
            altered_count = int(altered_str)
        except ValueError:
            errors_count = 0
            exceptions_count = 0
            created_count = 0
            altered_count = 0

        if line_errors or errors_count > 0 or exceptions_count > 0:
            err_msg = "; ".join(line_errors) if line_errors else f"Tally reported {errors_count} error(s), {exceptions_count} exception(s)"
            # Determine retryability: missing ledger is permanent, not retryable
            is_retryable = True
            if "does not exist" in err_msg.lower() or "not found" in err_msg.lower():
                is_retryable = False

            return TallyImportResult(
                success=False,
                created_count=created_count,
                altered_count=altered_count,
                error_message=err_msg,
                is_retryable=is_retryable,
            )

        if created_count > 0 or altered_count > 0:
            return TallyImportResult(
                success=True,
                created_count=created_count,
                altered_count=altered_count,
                last_vch_id=last_vch_id if last_vch_id != "0" else None,
            )

        # Neither created nor error reported (e.g. ignored)
        ignored_str = root.findtext(".//IGNORED") or "0"
        return TallyImportResult(
            success=False,
            error_message=f"Tally import resulted in no creation (ignored={ignored_str})",
            is_retryable=False,
        )

    def import_receipt(
        self, job_data: Dict[str, Any], company_name: Optional[str] = None
    ) -> TallyImportResult:
        """
        Executes end-to-end receipt import into Tally and retrieves created voucher identifiers.

        Checks for an existing FT:{payment_id} voucher first. A writeback job can be
        re-handed to us after a successful post whose backend ACK failed (cold start,
        timeout) or after a lease expired mid-post - in that case Tally already has the
        receipt, and re-sending would create a duplicate. Finding it first makes a
        re-claimed job self-heal (ack with the existing voucher) instead of double-posting.
        """
        payment_id = job_data.get("payment_id", "")
        precheck_date = job_data.get("payment_date", "").replace("-", "")
        existing = self.find_voucher_by_narration_marker(payment_id=payment_id, date_str=precheck_date)
        if existing:
            logger.warning(
                "Skipping Tally post for payment_id=%s: voucher already exists (GUID=%s VchNum=%s). "
                "Re-claimed job after a prior successful post (ack failure or lease expiry) - acking existing voucher.",
                payment_id,
                existing.get("guid"),
                existing.get("voucher_number"),
            )
            return TallyImportResult(
                success=True,
                created_count=0,
                guid=existing.get("guid"),
                voucher_number=existing.get("voucher_number"),
                master_id=existing.get("master_id"),
                alter_id=existing.get("alter_id"),
            )

        xml_payload = self.build_receipt_xml(job_data, company_name=company_name)
        logger.info(
            "Sending Receipt XML to Tally for payment_id=%s party=%s amount=%s",
            job_data.get("payment_id"),
            job_data.get("customer_name"),
            job_data.get("amount"),
        )
        response_text = self.send_xml(xml_payload)
        result = self.parse_import_response(response_text)

        # Handle Tally Educational Mode date restriction:
        # In Educational Mode without a silver/gold license, Tally strictly rejects any
        # voucher dated other than 1st, 2nd, or 31st/30th with:
        # "Voucher date is missing for: 'Receipt' voucher 1. Verify the data, resolve errors (if any) and retry Split."
        if not result.success and result.error_message and (
            "voucher date is missing" in result.error_message.lower()
            or "retry split" in result.error_message.lower()
        ):
            raw_dt = job_data.get("payment_date") or ""
            if raw_dt and len(raw_dt) >= 7:
                edu_date = f"{raw_dt[:7]}-01"
                logger.warning(
                    "Tally Educational Mode restriction detected (non-1st date %s rejected). "
                    "Auto-adjusting voucher date to %s for educational mode compatibility.",
                    raw_dt,
                    edu_date,
                )
                edu_job = dict(job_data)
                edu_job["payment_date"] = edu_date
                orig_notes = edu_job.get("notes") or ""
                edu_job["notes"] = f"[Tally EduMode: {edu_date} (Actual: {raw_dt})] {orig_notes}".strip()
                edu_xml = self.build_receipt_xml(edu_job, company_name=company_name)
                edu_resp = self.send_xml(edu_xml)
                edu_result = self.parse_import_response(edu_resp)
                if edu_result.success:
                    logger.info(
                        "Educational Mode retry SUCCEEDED with date %s for payment_id=%s",
                        edu_date,
                        job_data.get("payment_id"),
                    )
                    result = edu_result
                    job_data["payment_date"] = edu_date

        if not result.success:
            logger.warning(
                "Tally import rejected for payment_id=%s: %s (retryable=%s)",
                job_data.get("payment_id"),
                result.error_message,
                result.is_retryable,
            )
            return result

        # Retrieve created voucher details (GUID, Voucher Number, AlterID) from Tally
        payment_id = job_data.get("payment_id", "")
        payment_date = job_data.get("payment_date", "").replace("-", "")
        vch_details = self.find_voucher_by_narration_marker(
            payment_id=payment_id,
            date_str=payment_date,
        )

        if vch_details:
            result.guid = vch_details.get("guid")
            result.voucher_number = vch_details.get("voucher_number")
            result.master_id = vch_details.get("master_id") or result.last_vch_id
            result.alter_id = vch_details.get("alter_id")

        logger.info(
            "Tally import SUCCESS for payment_id=%s: GUID=%s VchNum=%s MasterID=%s",
            payment_id,
            result.guid,
            result.voucher_number,
            result.master_id,
        )
        return result

    def find_voucher_by_narration_marker(
        self, payment_id: str, date_str: str
    ) -> Optional[Dict[str, Any]]:
        """
        Finds a voucher created on date_str whose narration contains FT:{payment_id}.
        Returns GUID, MasterID, VoucherNumber, and AlterID.
        """
        query = f"""<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>SingleDayReceiptCol</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
        <SVCURRENTCOMPANY>SGRG SERVICES (OPC) PRIVATE LIMITED</SVCURRENTCOMPANY>
        <SVFROMDATE>{date_str}</SVFROMDATE>
        <SVTODATE>{date_str}</SVTODATE>
      </STATICVARIABLES>
      <TDL>
        <TDLMESSAGE>
          <COLLECTION NAME="SingleDayReceiptCol">
            <TYPE>Voucher</TYPE>
            <FETCH>VoucherNumber, Date, PartyLedgerName, Guid, MasterId, AlterId, VoucherTypeName, Amount, Narration, RemoteId</FETCH>
            <FILTER>IsReceiptVoucher</FILTER>
          </COLLECTION>
          <SYSTEM TYPE="Formulae" NAME="IsReceiptVoucher">$VoucherTypeName = "Receipt" OR $VoucherTypeName = "BANK RECEIPT" OR $$IsReceipt:$VoucherTypeName</SYSTEM>
        </TDLMESSAGE>
      </TDL>
    </DESC>
  </BODY>
</ENVELOPE>"""

        marker = f"FT:{payment_id}"
        remote_id_marker = f"ft_pmt_{payment_id}"
        try:
            root = self.execute_tdl(query)
            for v in root.findall(".//COLLECTION/VOUCHER"):
                narration = v.findtext("NARRATION") or ""
                remote_id = v.findtext("REMOTEID") or v.attrib.get("REMOTEID", "")
                if marker in narration or remote_id_marker == remote_id:
                    alter_id_str = (v.findtext("ALTERID") or "0").strip()
                    try:
                        alter_id = int(alter_id_str)
                    except ValueError:
                        alter_id = 0

                    return {
                        "guid": (v.findtext("GUID") or "").strip(),
                        "master_id": (v.findtext("MASTERID") or "").strip(),
                        "voucher_number": (v.findtext("VOUCHERNUMBER") or "").strip(),
                        "alter_id": alter_id,
                    }
        except Exception as ex:
            logger.warning(f"Error querying created voucher details from Tally: {ex}")

        return None

    def delete_voucher_by_guid_or_number(
        self,
        date_str: str,
        voucher_number: str,
        company_name: Optional[str] = None,
    ) -> bool:
        """
        Deletes a voucher in Tally by voucher number and date.
        Used for reversing test vouchers in Phase 9.
        """
        target_company = company_name or "SGRG SERVICES (OPC) PRIVATE LIMITED"
        delete_xml = f"""<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Import Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <IMPORTDATA>
      <REQUESTDESC>
        <REPORTNAME>Vouchers</REPORTNAME>
        <STATICVARIABLES>
          <SVCURRENTCOMPANY>{escape(target_company)}</SVCURRENTCOMPANY>
        </STATICVARIABLES>
      </REQUESTDESC>
      <REQUESTDATA>
        <TALLYMESSAGE xmlns:UDF="TallyUDF">
          <VOUCHER DATE="{date_str}" TAGNAME="Voucher Number" TAGVALUE="{escape(voucher_number)}" ACTION="Delete">
            <DATE>{date_str}</DATE>
            <VOUCHERNUMBER>{escape(voucher_number)}</VOUCHERNUMBER>
            <VOUCHERTYPENAME>Receipt</VOUCHERTYPENAME>
          </VOUCHER>
        </TALLYMESSAGE>
      </REQUESTDATA>
    </IMPORTDATA>
  </BODY>
</ENVELOPE>"""
        try:
            res_text = self.send_xml(delete_xml)
            root = ET.fromstring(res_text)
            deleted_count = int(root.findtext(".//DELETED") or "0")
            cancelled_count = int(root.findtext(".//CANCELLED") or "0")
            logger.info(
                "Delete voucher %s on %s result: deleted=%d cancelled=%d",
                voucher_number,
                date_str,
                deleted_count,
                cancelled_count,
            )
            return deleted_count > 0 or cancelled_count > 0
        except Exception as ex:
            logger.error(f"Failed to delete voucher {voucher_number} from Tally: {ex}")
            return False

    def resolve_sales_ledger(self, brand_name: Optional[str] = None) -> str:
        """
        Resolves the appropriate Sales ledger in SGRG TallyPrime based on the brand.
        """
        if not brand_name:
            return "Sales"
        b_low = brand_name.lower()
        if "usha" in b_low:
            return "USHA SALES"
        if "vu" in b_low:
            return "Sales VU"
        if "zebronic" in b_low or "zbr" in b_low:
            return "Sales ZBR"
        if "singer" in b_low:
            return "Singer Sales"
        return "Sales"

    def build_sales_order_xml(
        self, job_data: Dict[str, Any], company_name: Optional[str] = None
    ) -> str:
        """
        Generates standard Tally Import XML for a Sales Order voucher.
        Matches SGRG verified schema:
        - VCHTYPE: Sales Order
        - PARTYLEDGERNAME: Customer Name
        - INVENTORYENTRIES with STOCKITEMNAME, RATE, BILLEDQTY, ACTUALQTY, AMOUNT, BATCHALLOCATIONS (ORDERNO)
        - Balanced ledger offset
        """
        order_id = job_data.get("order_id", "")
        order_number = job_data.get("order_number", "")
        customer_name = job_data.get("customer_name", "").strip()
        order_date = job_data.get("order_date", "").replace("-", "") or datetime.now().strftime("%Y%m%d")
        total_amount = abs(float(job_data.get("total_amount", 0.0)))
        items = job_data.get("items", [])
        admin_notes = (job_data.get("admin_notes") or "").strip()

        target_company = company_name or "SGRG SERVICES (OPC) PRIVATE LIMITED"
        remote_id = f"ft_ord_{order_id}"
        narration = f"FieldTrack Confirmed Order {order_number} | FT:{order_id}"
        if admin_notes:
            narration += f" | {admin_notes}"

        # Build inventory entries XML
        inv_xml_blocks = []
        first_brand = None
        for it in items:
            s_name = it.get("stock_item_name") or f"{it.get('brand_name', '')} {it.get('product_model', '')}"
            first_brand = first_brand or it.get("brand_name")
            qty = it.get("quantity", 1)
            unit = it.get("unit", "PCS")
            rate = abs(float(it.get("rate", 0.0)))
            amt = abs(float(it.get("amount", rate * qty)))

            inv_xml_blocks.append(f"""          <ALLINVENTORYENTRIES.LIST>
            <STOCKITEMNAME>{escape(s_name)}</STOCKITEMNAME>
            <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
            <RATE>{rate:.2f}/{unit}</RATE>
            <BILLEDQTY> {qty} {unit}</BILLEDQTY>
            <ACTUALQTY> {qty} {unit}</ACTUALQTY>
            <AMOUNT>{amt:.2f}</AMOUNT>
            <BATCHALLOCATIONS.LIST>
              <ORDERNO>{escape(order_number)}</ORDERNO>
              <TRACKINGNUMBER> Not Applicable</TRACKINGNUMBER>
              <GODOWNNAME>Main Location</GODOWNNAME>
              <AMOUNT>{amt:.2f}</AMOUNT>
              <ACTUALQTY> {qty} {unit}</ACTUALQTY>
              <BILLEDQTY> {qty} {unit}</BILLEDQTY>
            </BATCHALLOCATIONS.LIST>
          </ALLINVENTORYENTRIES.LIST>""")

        inventory_xml = "\n".join(inv_xml_blocks)
        sales_ledger = self.resolve_sales_ledger(first_brand)

        return f"""<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Import Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <IMPORTDATA>
      <REQUESTDESC>
        <REPORTNAME>Vouchers</REPORTNAME>
        <STATICVARIABLES>
          <SVCURRENTCOMPANY>{escape(target_company)}</SVCURRENTCOMPANY>
        </STATICVARIABLES>
      </REQUESTDESC>
      <REQUESTDATA>
        <TALLYMESSAGE xmlns:UDF="TallyUDF">
          <VOUCHER DATE="{order_date}" REMOTEID="{escape(remote_id)}" VCHTYPE="Sales Order" ACTION="Create" OBJVIEW="Invoice Voucher View">
            <DATE>{order_date}</DATE>
            <EFFECTIVEDATE>{order_date}</EFFECTIVEDATE>
            <VOUCHERTYPENAME>Sales Order</VOUCHERTYPENAME>
            <PARTYLEDGERNAME>{escape(customer_name)}</PARTYLEDGERNAME>
            <PARTYNAME>{escape(customer_name)}</PARTYNAME>
            <BASICBUYERNAME>{escape(customer_name)}</BASICBUYERNAME>
            <REFERENCE>{escape(order_number)}</REFERENCE>
            <NARRATION>{escape(narration)}</NARRATION>
            <ISOPTIONAL>No</ISOPTIONAL>
            <ISINVOICE>No</ISINVOICE>
{inventory_xml}
            <!-- Customer Party Entry (Debit) -->
            <ALLLEDGERENTRIES.LIST>
              <LEDGERNAME>{escape(customer_name)}</LEDGERNAME>
              <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
              <AMOUNT>-{total_amount:.2f}</AMOUNT>
              <BILLALLOCATIONS.LIST>
                <NAME>On Account</NAME>
                <BILLTYPE>On Account</BILLTYPE>
                <AMOUNT>-{total_amount:.2f}</AMOUNT>
              </BILLALLOCATIONS.LIST>
            </ALLLEDGERENTRIES.LIST>
            <!-- Sales Account Entry (Credit) -->
            <ALLLEDGERENTRIES.LIST>
              <LEDGERNAME>{escape(sales_ledger)}</LEDGERNAME>
              <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
              <AMOUNT>{total_amount:.2f}</AMOUNT>
            </ALLLEDGERENTRIES.LIST>
          </VOUCHER>
        </TALLYMESSAGE>
      </REQUESTDATA>
    </IMPORTDATA>
  </BODY>
</ENVELOPE>"""

    def import_sales_order(
        self, job_data: Dict[str, Any], company_name: Optional[str] = None
    ) -> TallyImportResult:
        """
        Executes end-to-end Sales Order import into TallyPrime and retrieves created voucher identifiers.

        Checks for an existing FT:{order_id} voucher first - see import_receipt() for why
        (a re-claimed job may already have been posted successfully).
        """
        order_id = job_data.get("order_id", "")
        precheck_date = job_data.get("order_date", "").replace("-", "")
        existing = self.find_order_by_marker(order_id=order_id, date_str=precheck_date)
        if existing:
            logger.warning(
                "Skipping Tally post for order_id=%s: voucher already exists (GUID=%s VchNum=%s). "
                "Re-claimed job after a prior successful post (ack failure or lease expiry) - acking existing voucher.",
                order_id,
                existing.get("guid"),
                existing.get("voucher_number"),
            )
            return TallyImportResult(
                success=True,
                created_count=0,
                guid=existing.get("guid"),
                voucher_number=existing.get("voucher_number"),
                master_id=existing.get("master_id"),
                alter_id=existing.get("alter_id"),
            )

        xml_payload = self.build_sales_order_xml(job_data, company_name=company_name)
        logger.info(
            "Sending Sales Order XML to Tally for order_id=%s order_num=%s party=%s amount=%s",
            job_data.get("order_id"),
            job_data.get("order_number"),
            job_data.get("customer_name"),
            job_data.get("total_amount"),
        )
        response_text = self.send_xml(xml_payload)
        result = self.parse_import_response(response_text)

        # Handle Tally Educational Mode date restriction for Sales Orders
        if not result.success and result.error_message and (
            "voucher date is missing" in result.error_message.lower()
            or "retry split" in result.error_message.lower()
        ):
            raw_dt = job_data.get("order_date") or ""
            if raw_dt and len(raw_dt) >= 7:
                edu_date = f"{raw_dt[:7]}-01"
                logger.warning(
                    "Tally Educational Mode restriction detected on Sales Order. Auto-adjusting to %s.",
                    edu_date,
                )
                edu_job = dict(job_data)
                edu_job["order_date"] = edu_date
                edu_xml = self.build_sales_order_xml(edu_job, company_name=company_name)
                edu_resp = self.send_xml(edu_xml)
                edu_result = self.parse_import_response(edu_resp)
                if edu_result.success:
                    result = edu_result
                    job_data["order_date"] = edu_date

        if not result.success:
            logger.warning(
                "Tally import rejected for order_id=%s: %s (retryable=%s)",
                job_data.get("order_id"),
                result.error_message,
                result.is_retryable,
            )
            return result

        # Query created voucher details
        order_id = job_data.get("order_id", "")
        order_date = job_data.get("order_date", "").replace("-", "")
        vch_details = self.find_order_by_marker(order_id=order_id, date_str=order_date)

        if vch_details:
            result.guid = vch_details.get("guid")
            result.voucher_number = vch_details.get("voucher_number")
            result.master_id = vch_details.get("master_id") or result.last_vch_id
            result.alter_id = vch_details.get("alter_id")

        logger.info(
            "Tally Sales Order import SUCCESS for order_id=%s: GUID=%s VchNum=%s MasterID=%s",
            order_id,
            result.guid,
            result.voucher_number,
            result.master_id,
        )
        return result

    def find_order_by_marker(
        self, order_id: str, date_str: str
    ) -> Optional[Dict[str, Any]]:
        """
        Finds a Sales Order voucher created on date_str whose narration or remoteid contains FT:{order_id}.
        """
        query = f"""<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>SingleDayOrderCol</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
        <SVCURRENTCOMPANY>SGRG SERVICES (OPC) PRIVATE LIMITED</SVCURRENTCOMPANY>
        <SVFROMDATE>{date_str}</SVFROMDATE>
        <SVTODATE>{date_str}</SVTODATE>
      </STATICVARIABLES>
      <TDL>
        <TDLMESSAGE>
          <COLLECTION NAME="SingleDayOrderCol">
            <TYPE>Voucher</TYPE>
            <FETCH>VoucherNumber, Date, PartyLedgerName, Guid, MasterId, AlterId, VoucherTypeName, Amount, Narration, RemoteId</FETCH>
            <FILTER>IsOrderVoucher</FILTER>
          </COLLECTION>
          <SYSTEM TYPE="Formulae" NAME="IsOrderVoucher">$VoucherTypeName = "Sales Order"</SYSTEM>
        </TDLMESSAGE>
      </TDL>
    </DESC>
  </BODY>
</ENVELOPE>"""
        marker = f"FT:{order_id}"
        remote_id_marker = f"ft_ord_{order_id}"
        try:
            root = self.execute_tdl(query)
            for v in root.findall(".//COLLECTION/VOUCHER"):
                narration = v.findtext("NARRATION") or ""
                remote_id = v.findtext("REMOTEID") or v.attrib.get("REMOTEID", "")
                if marker in narration or remote_id_marker == remote_id:
                    alter_id_str = (v.findtext("ALTERID") or "0").strip()
                    try:
                        alter_id = int(alter_id_str)
                    except ValueError:
                        alter_id = 0

                    return {
                        "guid": (v.findtext("GUID") or "").strip(),
                        "master_id": (v.findtext("MASTERID") or "").strip(),
                        "voucher_number": (v.findtext("VOUCHERNUMBER") or "").strip(),
                        "alter_id": alter_id,
                    }
        except Exception as ex:
            logger.warning(f"Error querying created sales order details from Tally: {ex}")

        return None
