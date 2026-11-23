"""H2 Tally access: the test-only WRITE driver and an independent READER (own Export requests, not the agent's code).

Every write: (1) re-asserts the lock (exactly FT H2 TEST 3.0 / 58848a1b-..., right folder, no SGRG), (2) refuses any
voucher date that Educational Mode would reject (only the 1st, 2nd, 31st), (3) is logged to results/driver_writes.jsonl.
Voucher identity: REMOTEID (= the voucher GUID in Tally) of the form <company guid>-h2-<8 hex>; alter / cancel /
delete address the voucher by that REMOTEID only.
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

import h2_safety as hs

HERE = Path(__file__).resolve().parent
LOG = HERE / "results" / "driver_writes.jsonl"
COMPANY = hs.LOCK["company_name"]
EDU_DAYS = (1, 2, 31)
ILLEGAL = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]|&#(?:[0-8]|1[124-9]|2[0-9]|3[01]);")


class DriverError(RuntimeError):
    pass


def _post(xml: str, timeout: int = 120) -> str:
    req = urllib.request.Request(hs.LOCK["tally_url"], data=xml.encode("utf-8"), method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _root(text: str) -> ET.Element:
    return ET.fromstring(re.sub(r"<(/?)(\w+):", r"<\1\2_", ILLEGAL.sub("", text)))


def d8(d: date) -> str:
    return d.strftime("%Y%m%d")


def tday(d: date) -> str:
    return d.strftime("%d-%b-%Y")


def amt(x) -> str:
    return f"{Decimal(x):.2f}"


# ====================================================================================== WRITE
class Driver:
    def __init__(self):
        LOG.parent.mkdir(exist_ok=True)
        self.n = 0

    def _import(self, report: str, body: str, what: str) -> Dict[str, int]:
        hs.assert_test_company()                                    # lock, before EVERY write
        xml = (f"<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER><BODY><IMPORTDATA><REQUESTDESC>"
               f"<REPORTNAME>{report}</REPORTNAME><STATICVARIABLES><SVCURRENTCOMPANY>{escape(COMPANY)}</SVCURRENTCOMPANY>"
               f"</STATICVARIABLES></REQUESTDESC><REQUESTDATA><TALLYMESSAGE xmlns:UDF=\"TallyUDF\">{body}"
               f"</TALLYMESSAGE></REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>")
        resp = _post(xml)
        r = _root(resp)
        res = {k.lower(): int((r.findtext(f".//{k}") or "0").strip() or 0)
               for k in ("CREATED", "ALTERED", "DELETED", "CANCELLED", "ERRORS", "EXCEPTIONS", "IGNORED", "COMBINED")}
        errs = [e.text.strip() for e in r.iter("LINEERROR") if e.text and e.text.strip()]
        rec = {"at": datetime.now().isoformat(timespec="seconds"), "what": what, "result": res, "line_errors": errs}
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        if errs or res["errors"] or res["exceptions"]:
            raise DriverError(f"Tally refused {what}: {errs or res}")
        return res

    # ---------------------------------------------------------------- masters
    def ledger(self, name: str, parent: str, opening: Decimal = Decimal("0"), billwise: bool = False,
               opening_bill: Optional[str] = None) -> Dict[str, int]:
        bills = ""
        if billwise and opening and opening_bill:
            bills = (f"<BILLALLOCATIONS.LIST><BILLDATE>{d8(date(2026, 4, 1))}</BILLDATE><NAME>{escape(opening_bill)}</NAME>"
                     f"<OPENINGBALANCE>{amt(opening)}</OPENINGBALANCE><ISADVANCE>No</ISADVANCE></BILLALLOCATIONS.LIST>")
        body = (f'<LEDGER NAME="{escape(name)}" ACTION="Create"><NAME.LIST><NAME>{escape(name)}</NAME></NAME.LIST>'
                f"<PARENT>{escape(parent)}</PARENT><ISBILLWISEON>{'Yes' if billwise else 'No'}</ISBILLWISEON>"
                f"<OPENINGBALANCE>{amt(opening)}</OPENINGBALANCE>{bills}</LEDGER>")
        return self._import("All Masters", body, f"ledger {name}")

    # ---------------------------------------------------------------- vouchers
    @staticmethod
    def check_date(d: date) -> None:
        if d.day not in EDU_DAYS:
            raise DriverError(f"refused: {d} is not an Educational Mode date (1st, 2nd, 31st only)")

    def new_id(self) -> str:
        self.n += 1
        return f"{hs.LOCK['company_guid']}-h2-{int(time.time() * 1000) % 0xFFFFFF:06x}{self.n:04x}"

    @staticmethod
    def _lines_xml(lines: List[dict]) -> str:
        out = []
        for ln in lines:                       # amount: Tally sign (negative = debit)
            a = Decimal(ln["amount"])
            bills = "".join(f"<BILLALLOCATIONS.LIST><NAME>{escape(b[0])}</NAME><BILLTYPE>{b[1]}</BILLTYPE>"
                            f"<AMOUNT>{amt(b[2])}</AMOUNT></BILLALLOCATIONS.LIST>" for b in ln.get("bills", []))
            out.append(f"<ALLLEDGERENTRIES.LIST><LEDGERNAME>{escape(ln['ledger'])}</LEDGERNAME>"
                       f"<ISDEEMEDPOSITIVE>{'Yes' if a < 0 else 'No'}</ISDEEMEDPOSITIVE><AMOUNT>{amt(a)}</AMOUNT>"
                       f"{bills}</ALLLEDGERENTRIES.LIST>")
        return "".join(out)

    def _voucher_body(self, action, vtype, d, lines, narration, party, number=None, attr_date=None):
        self.check_date(d)
        if sum(Decimal(l["amount"]) for l in lines) != 0:
            raise DriverError(f"unbalanced voucher ({vtype} {d} {narration})")
        p = f"<PARTYLEDGERNAME>{escape(party)}</PARTYLEDGERNAME>" if party else ""
        tag = (f' DATE="{d8(attr_date or d)}" TAGNAME="Voucher Number" TAGVALUE="{escape(number)}"' if number else "")
        num = f"<VOUCHERNUMBER>{escape(number)}</VOUCHERNUMBER>" if number else ""
        return (f'<VOUCHER{tag} VCHTYPE="{vtype}" ACTION="{action}" OBJVIEW="Accounting Voucher View">'
                f"<DATE>{d8(d)}</DATE><EFFECTIVEDATE>{d8(d)}</EFFECTIVEDATE><VOUCHERTYPENAME>{vtype}</VOUCHERTYPENAME>"
                f"{num}{p}<NARRATION>{escape(narration)}</NARRATION>"
                f"<PERSISTEDVIEW>Accounting Voucher View</PERSISTEDVIEW>{self._lines_xml(lines)}</VOUCHER>")

    def create(self, vtype: str, d: date, lines: List[dict], narration: str, party: Optional[str] = None) -> dict:
        """Creates a voucher; narration must carry a unique marker. -> {guid, number, alter, date} read back from Tally."""
        res = self._import("Vouchers", self._voucher_body("Create", vtype, d, lines, narration, party),
                           f"Create {vtype} {d} '{narration}'")
        if res["created"] != 1:
            raise DriverError(f"create {vtype} {d}: {res}")
        hits = [v for v in voucher_map(d, d).values() if (v["elem"].findtext("NARRATION") or "") == narration]
        if len(hits) != 1:
            raise DriverError(f"created voucher '{narration}' found {len(hits)} times")
        v = hits[0]
        out = {"guid": v["guid"], "number": v["number"], "alter": v["alter"], "date": v["date"], "vtype": vtype}
        _ledger("created", out)
        return out

    def alter(self, vtype: str, number: str, old_date: date, new_date: date, lines: List[dict], narration: str,
              party: Optional[str] = None) -> Dict[str, int]:
        self.check_date(old_date)
        res = self._import("Vouchers", self._voucher_body("Alter", vtype, new_date, lines, narration, party, number, old_date),
                           f"Alter {vtype} no.{number} {old_date}->{new_date}")
        if res["altered"] != 1:
            raise DriverError(f"alter {vtype} no.{number}: {res}")
        return res

    def _by_number(self, action: str, vtype: str, number: str, d: date) -> Dict[str, int]:
        self.check_date(d)
        body = (f'<VOUCHER DATE="{d8(d)}" TAGNAME="Voucher Number" TAGVALUE="{escape(number)}" '
                f'VCHTYPE="{vtype}" ACTION="{action}"><DATE>{d8(d)}</DATE><VOUCHERTYPENAME>{vtype}</VOUCHERTYPENAME>'
                f"<VOUCHERNUMBER>{escape(number)}</VOUCHERNUMBER></VOUCHER>")
        return self._import("Vouchers", body, f"{action} {vtype} no.{number} {d}")

    def cancel(self, vtype: str, number: str, d: date) -> Dict[str, int]:
        return self._by_number("Cancel", vtype, number, d)

    def delete(self, vtype: str, number: str, d: date) -> Dict[str, int]:
        hits = [v for v in voucher_map(d, d).values() if v["number"] == number and v["vtype"] == vtype]
        if len(hits) != 1:
            raise DriverError(f"delete {vtype} no.{number} {d}: found {len(hits)} vouchers")
        res = self._by_number("Delete", vtype, number, d)
        if res["deleted"] != 1:
            raise DriverError(f"delete {vtype} no.{number}: {res}")
        _ledger("deleted", {"guid": hits[0]["guid"], "number": number, "vtype": vtype, "date": str(d)})
        return res


VOUCHER_LEDGER = HERE / "results" / "driver_vouchers.jsonl"


def _ledger(event: str, rec: dict) -> None:
    with VOUCHER_LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": datetime.now().isoformat(timespec="seconds"), "event": event, **rec}) + "\n")


def expected_guids_from_ledger(pre_existing: set) -> set:
    """GUIDs that must exist in Tally: pre-existing + created - deleted (from the driver's own voucher ledger)."""
    s = set(pre_existing)
    if VOUCHER_LEDGER.exists():
        for line in VOUCHER_LEDGER.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            (s.add if r["event"] == "created" else s.discard)(r["guid"])
    return s


# ====================================================================================== READ (independent)
def _export_collection(cid: str, typ: str, fetch: str, sv: str = "", extra: str = "") -> ET.Element:
    hs.assert_test_company()
    xml = (f"<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>{cid}</ID>"
           f"</HEADER><BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>"
           f"<SVCURRENTCOMPANY>{escape(COMPANY)}</SVCURRENTCOMPANY>{sv}</STATICVARIABLES><TDL><TDLMESSAGE>"
           f'<COLLECTION NAME="{cid}" ISMODIFY="No"><TYPE>{typ}</TYPE><FETCH>{fetch}</FETCH>{extra}</COLLECTION>'
           f"</TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>")
    return _root(_post(xml, timeout=300))


def raw_export(cid, typ, fetch, sv="", extra="") -> str:
    return ET.tostring(_export_collection(cid, typ, fetch, sv, extra), encoding="unicode")


def read_vouchers(d_from: date, d_to: date) -> List[ET.Element]:
    sv = f'<SVFROMDATE TYPE="Date">{tday(d_from)}</SVFROMDATE><SVTODATE TYPE="Date">{tday(d_to)}</SVTODATE>'
    extra = (f'<FILTER>H2Range</FILTER></COLLECTION><SYSTEM TYPE="Formulae" NAME="H2Range">'
             f'$Date &gt;= $$Date:"{tday(d_from)}" AND $Date &lt;= $$Date:"{tday(d_to)}"</SYSTEM><COLLECTION NAME="_x">')
    fetch = ("Date, Guid, VoucherNumber, VoucherTypeName, PartyLedgerName, Narration, IsCancelled, IsOptional, AlterId, "
             "Amount, AllLedgerEntries.LedgerName, AllLedgerEntries.Amount, AllLedgerEntries.BillAllocations.Name, "
             "AllLedgerEntries.BillAllocations.BillType, AllLedgerEntries.BillAllocations.Amount")
    root = _export_collection("H2Vch", "Voucher", fetch, sv, extra)
    return [v for v in root.iter("VOUCHER") if len(v) and (v.findtext("GUID") or "").strip()]


def read_debtors_raw(as_of: Optional[date] = None) -> str:
    """Debtor ledgers; ClosingBalance as of `as_of` (must be an Educational-Mode day) from 1 Apr 2026."""
    sv = (f'<SVFROMDATE TYPE="Date">{tday(date(2026, 4, 1))}</SVFROMDATE><SVTODATE TYPE="Date">{tday(as_of)}</SVTODATE>'
          if as_of else "")
    if as_of and as_of.day not in EDU_DAYS:
        raise DriverError(f"as_of {as_of} is not an Educational Mode day")
    return raw_export("H2Deb", "Ledger", "Name, Parent, Guid, OpeningBalance, ClosingBalance, BillAllocations.Name, "
                      "BillAllocations.OpeningBalance", sv=sv,
                      extra='<FILTER>H2IsDeb</FILTER></COLLECTION><SYSTEM TYPE="Formulae" NAME="H2IsDeb">'
                            '$$IsBelongsTo:$$GroupSundryDebtors</SYSTEM><COLLECTION NAME="_y">')


def read_vtypes_raw() -> str:
    return raw_export("H2VchT", "VoucherType", "Name, Parent")


def voucher_map(d_from: date, d_to: date) -> Dict[str, dict]:
    out = {}
    for v in read_vouchers(d_from, d_to):
        g = v.findtext("GUID").strip()
        dd = (v.findtext("DATE") or "").strip()
        out[g] = {"guid": g, "date": f"{dd[:4]}-{dd[4:6]}-{dd[6:]}", "alter": int((v.findtext("ALTERID") or "0").strip() or 0),
                  "vtype": (v.findtext("VOUCHERTYPENAME") or "").strip(), "number": (v.findtext("VOUCHERNUMBER") or "").strip(),
                  "cancelled": (v.findtext("ISCANCELLED") or "").strip().lower() == "yes", "elem": v}
    return out
