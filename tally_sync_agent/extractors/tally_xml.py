"""
Agent 2.2.1 - Tally XML requests and parsers (read-only: every request is TALLYREQUEST=Export).

Request forms, each PROVEN on the client's TallyPrime (Phase 0, 18 Nov 2026, 173 raw files,
release_v2/agent_2.2.0/PHASE0_FINDINGS_AND_PLAN_2.2.0.md):

* COLLECTIONS with period values (vouchers - one day, date range, AlterID - and debtor /
  creditor ledgers with balances) carry the TYPED period plus the company:
      <SVFROMDATE TYPE="Date">1-Apr-2025</SVFROMDATE><SVTODATE TYPE="Date">31-Mar-2026</SVTODATE>
      <SVCURRENTCOMPANY>...</SVCURRENTCOMPANY>
  Proof: per-ledger sums equal Tally's Group Summary to the paisa in FY 2025-26 and 2026-27;
  closing FY 2025-26 = opening FY 2026-27 for 1,599 debtors; voucher counts 3 / 14,905 / 22,753.
  The UNTYPED form (YYYYMMDD, 2.1.1/2.1.2) is NEVER used for collections: vouchers came back
  only for the current FY and balances came back as today's balance in every FY, opening ==
  closing (R11, R2b). No collection is ever built without a scope (R1).
* REPORTS (Bills Receivable, Bills Payable, Group Summary) use the TYPED dates too (2.2.1, A3/A4).
  Proof (18-Nov probes): Bills Receivable / Payable "as of" a PAST date in the untyped form returned
  bills dated AFTER that date (31-Mar-2025: 2,080 receivable and 244 payable bills, all later); the
  typed form SVFROMDATE=books start .. SVTODATE=as-of was correct at 31-Mar-2025 (empty, Group Summary
  0), 31-Mar-2026 (latest bill 31-Mar-2026) and today. Group Summary: both forms identical at all
  three dates; the typed form is used for consistency. The untyped report form is no longer built.
* VOUCHER requests (2.2.1, B1/B11/B10): the typed period of every voucher request is the day (or the
  month / date range) it asks for, not the whole FY - proven identical (GUIDs, parsed payloads, totals)
  on 6 days and a month, and 3-10x less Tally time. The LEAN fetch (header + ledger name/amount + bill
  and bank allocations) is proven identical to the wildcard fetch on 5 days (1,312 vouchers) at a
  quarter of the size. A voucher request WITHOUT a date filter is refused, and an AlterID filter must
  be a positive integer: the 2.1.0 checkpoint-0 request (no filter at all) cannot be built.
* MASTERS without period values (groups, all ledgers, voucher types) are unchanged from
  2.0: proven to return the full lists. The agent refuses to run when more than one company
  is loaded, so an unscoped master list cannot come from another company.
* A FILTER formula `$Date = $$Date:"13-Nov-2026"` limits a voucher collection to one day;
  `$$Number:$AlterId > N` to changed vouchers; the wildcard sub-list fetch returns bill and
  bank allocations; the debtor collection needs CHILDOF (the 1.x CHILDROF typo returned all).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional
from xml.sax.saxutils import escape

VOUCHER_HEADER_FETCH = "Date, Guid, VoucherNumber, VoucherTypeName, PartyLedgerName, Amount, Narration, IsCancelled, IsOptional, AlterId"
# 2.2.0 wildcard fetch, kept only as the reference the lean fetch was proven against (never sent by 2.2.1).
VOUCHER_WILDCARD_FETCH = VOUCHER_HEADER_FETCH + ", AllLedgerEntries.*, AllLedgerEntries.BillAllocations.*, AllLedgerEntries.BankAllocations.*"
# 2.2.1 lean fetch (B1): exactly what the parser reads.
VOUCHER_LEAN_FETCH = (VOUCHER_HEADER_FETCH + ", AllLedgerEntries.LedgerName, AllLedgerEntries.Amount, "
                      "AllLedgerEntries.BillAllocations.*, AllLedgerEntries.BankAllocations.*")
VOUCHER_FULL_FETCH = VOUCHER_LEAN_FETCH
MANIFEST_FETCH = "Date, Guid, VoucherTypeName, IsCancelled, IsOptional, AlterId"

DEBTOR_FETCH = (
    "Name, Guid, Parent, AlterId, OpeningBalance, ClosingBalance, IsBillWiseOn, BillCreditPeriod, "
    "LedgerMobile, Email, LedGstRegDetails.List, LanguageName.List, Address.List, PinCode, StateName, "
    "LedgerPhone, Mobile, LedgerContact, PartyGstin, LedMailingDetails.List"
)
CREDITOR_FETCH = (
    "Name, Guid, Parent, AlterId, OpeningBalance, ClosingBalance, IsBillWiseOn, BillCreditPeriod, "
    "LedgerMobile, Email, LedGstRegDetails.List, Address.List, PinCode, StateName, LedgerPhone, PartyGstin"
)
ALL_LEDGER_FETCH = "Name, Parent, Guid, LanguageName.List"

# Reserved Tally groups used to classify the counter ledger of a receipt.
CASH_GROUPS = {"cash-in-hand"}
BANK_GROUPS = {"bank accounts", "bank od a/c", "bank occ a/c"}

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def tally_day(d: date) -> str:
    """13-Nov-2026 (the form used inside $$Date: formulas and the typed period variables)."""
    return f"{d.day}-{_MONTHS[d.month - 1]}-{d.year}"


def ymd8(d: date) -> str:
    return d.strftime("%Y%m%d")


@dataclass(frozen=True)
class Scope:
    """The financial-year period and the company a COLLECTION is evaluated in."""
    period_from: date
    period_to: date
    company: str

    def __post_init__(self):
        if self.period_to < self.period_from:
            raise ValueError("period_to is before period_from")
        if not (self.company or "").strip():
            raise ValueError("a Scope needs the company name")


def collection_scope_vars(scope: Scope) -> str:
    """The proven typed form (Phase 0 variant T)."""
    return (f'<SVFROMDATE TYPE="Date">{tally_day(scope.period_from)}</SVFROMDATE>'
            f'<SVTODATE TYPE="Date">{tally_day(scope.period_to)}</SVTODATE>'
            f"<SVCURRENTCOMPANY>{escape(scope.company)}</SVCURRENTCOMPANY>")


def typed_dates(from_date: date, to_date: date) -> str:
    if to_date < from_date:
        raise ValueError("to_date is before from_date")
    return (f'<SVFROMDATE TYPE="Date">{tally_day(from_date)}</SVFROMDATE>'
            f'<SVTODATE TYPE="Date">{tally_day(to_date)}</SVTODATE>')


def report_vars(to_date: date, from_date: date, company: Optional[str] = None) -> str:
    """2.2.1 report form: TYPED from/to dates (+ company). from_date is required (A3: the untyped
    to-date-only form ignored past as-of dates)."""
    if from_date is None:
        raise ValueError("a report needs an explicit from_date (typed form, A3)")
    out = typed_dates(from_date, to_date)
    if company:
        out += f"<SVCURRENTCOMPANY>{escape(company)}</SVCURRENTCOMPANY>"
    return out


def _require_scope(scope: Optional[Scope], what: str) -> Scope:
    if not isinstance(scope, Scope):
        raise ValueError(f"{what} needs an explicit Scope (FY period + company): never rely on Tally's session (R1)")
    return scope


def _envelope_collection(cid: str, collection_body: str, formulae: str = "", static_vars: str = "") -> str:
    return (
        "<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE>"
        f"<ID>{cid}</ID></HEADER><BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>"
        f"{static_vars}</STATICVARIABLES><TDL><TDLMESSAGE>{collection_body}{formulae}</TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>"
    )


def _envelope_report(report_id: str, static_vars: str) -> str:
    return (
        "<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Data</TYPE>"
        f"<ID>{report_id}</ID></HEADER><BODY><DESC><STATICVARIABLES>"
        f"<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>{static_vars}"
        "</STATICVARIABLES></DESC></BODY></ENVELOPE>"
    )


class UnfilteredRequestRefused(ValueError):
    """A voucher request without a date filter, or with a missing / zero / negative / non-integer AlterID
    filter, is never built (B10: 2.1.0 sent an unfiltered whole-period request at checkpoint 0)."""


def _alter_id(min_alter_id: Any) -> int:
    if isinstance(min_alter_id, bool) or not isinstance(min_alter_id, int) or min_alter_id <= 0:
        raise UnfilteredRequestRefused(f"AlterID filter must be a positive integer, got {min_alter_id!r}")
    return min_alter_id


def voucher_request(fetch: str, day: Optional[date] = None, min_alter_id: Optional[int] = None,
                    date_from: Optional[date] = None, date_to: Optional[date] = None,
                    scope: Optional[Scope] = None) -> str:
    """One day (`day`) or an inclusive date range (`date_from`..`date_to`), optionally AND AlterID > N.
    `scope` is the FY (+ company) the dates must lie in; the request itself is evaluated in a typed
    period equal to the day / range (B11), with the same $Date filter as a second guard.
    No date filter -> UnfilteredRequestRefused. min_alter_id given -> must be a positive int."""
    sc = _require_scope(scope, "a voucher request")
    if (date_from is None) != (date_to is None):
        raise ValueError("date_from and date_to go together")
    if day is not None and date_from is not None:
        raise ValueError("use either day or a date range")
    if day is None and date_from is None:
        raise UnfilteredRequestRefused("a voucher request needs a day or a date range (never the whole period unfiltered)")
    a, b = (day, day) if day is not None else (date_from, date_to)
    if b < a:
        raise ValueError("date_to is before date_from")
    for d in (a, b):
        if not (sc.period_from <= d <= sc.period_to):
            raise ValueError(f"date {d} is outside the scope {sc.period_from}..{sc.period_to}")
    # Filter names and formulae are byte-identical to the requests proven by the 18-Nov day-scope probe.
    if a == b:
        filters = "<FILTER>FtpDay</FILTER>"
        formulae = f'<SYSTEM TYPE="Formulae" NAME="FtpDay">$Date = $$Date:"{tally_day(a)}"</SYSTEM>'
    else:
        filters = "<FILTER>FtpRange</FILTER>"
        formulae = (f'<SYSTEM TYPE="Formulae" NAME="FtpRange">$Date &gt;= $$Date:"{tally_day(a)}"'
                    f' AND $Date &lt;= $$Date:"{tally_day(b)}"</SYSTEM>')
    if min_alter_id is not None:
        n = _alter_id(min_alter_id)
        filters += "<FILTER>FtpAlter</FILTER>"
        formulae += f'<SYSTEM TYPE="Formulae" NAME="FtpAlter">$$Number:$AlterId &gt; {n}</SYSTEM>'
    body = f'<COLLECTION NAME="FtpVch"><TYPE>Voucher</TYPE><FETCH>{fetch}</FETCH>{filters}</COLLECTION>'
    request_scope = Scope(a, b, sc.company)
    return _envelope_collection("FtpVch", body, formulae, collection_scope_vars(request_scope))


def _ledger_group_request(cid: str, group_fn: str, fetch: str, min_alter_id: Optional[int], scope: Optional[Scope]) -> str:
    sc = _require_scope(scope, f"the {cid} request")
    filters, formulae = "", ""
    if min_alter_id is not None and min_alter_id != 0:
        n = _alter_id(min_alter_id)  # masters: None/0 = all debtors (a small, bounded list); negative refused
        filters = "<FILTER>FtpAlterId</FILTER>"
        formulae = f'<SYSTEM TYPE="Formulae" NAME="FtpAlterId">$$Number:$AlterId &gt; {n}</SYSTEM>'
    body = (f'<COLLECTION NAME="{cid}"><TYPE>Ledger</TYPE><CHILDOF>{group_fn}</CHILDOF>'
            f"<BELONGSTO>Yes</BELONGSTO><FETCH>{fetch}</FETCH>{filters}</COLLECTION>")
    return _envelope_collection(cid, body, formulae, collection_scope_vars(sc))


def debtors_request(min_alter_id: Optional[int] = None, scope: Optional[Scope] = None) -> str:
    """Sundry Debtors with OpeningBalance (at the FY start) and ClosingBalance (at the FY end)."""
    return _ledger_group_request("FtpDebtors", "$$GroupSundryDebtors", DEBTOR_FETCH, min_alter_id, scope)


def creditors_request(scope: Optional[Scope] = None) -> str:
    """Sundry Creditors with balances (2.2.0: local validation / reporting only, never uploaded)."""
    return _ledger_group_request("FtpCreditors", "$$GroupSundryCreditors", CREDITOR_FETCH, None, scope)


def all_ledgers_request() -> str:
    return _envelope_collection(
        "FtpLedgers", f'<COLLECTION NAME="FtpLedgers"><TYPE>Ledger</TYPE><FETCH>{ALL_LEDGER_FETCH}</FETCH></COLLECTION>'
    )


def groups_request() -> str:
    return _envelope_collection(
        "FtpGroups", '<COLLECTION NAME="FtpGroups"><TYPE>Group</TYPE><FETCH>Name, Parent, Guid</FETCH></COLLECTION>'
    )


def voucher_types_request() -> str:
    return _envelope_collection(
        "FtpVchTypes",
        '<COLLECTION NAME="FtpVchTypes"><TYPE>VoucherType</TYPE><FETCH>Name, Parent, Guid, IsActive</FETCH></COLLECTION>',
    )


def company_request() -> str:
    return _envelope_collection(
        "CompanyCol",
        '<COLLECTION NAME="CompanyCol"><TYPE>Company</TYPE><FETCH>Name, Guid, StartingDate, EndingDate, BooksFrom</FETCH></COLLECTION>',
    )


def bills_receivable_request(as_of: date, company: Optional[str] = None, books_from: Optional[date] = None) -> str:
    """Typed SVFROMDATE = books start, SVTODATE = as-of (A3, proven on 18-Nov). books_from is required."""
    if books_from is None:
        raise ValueError("bills_receivable_request needs books_from (typed form, A3)")
    return _envelope_report("Bills Receivable", report_vars(as_of, books_from, company))


def bills_payable_request(as_of: date, company: Optional[str] = None, books_from: Optional[date] = None) -> str:
    if books_from is None:
        raise ValueError("bills_payable_request needs books_from (typed form, A3)")
    return _envelope_report("Bills Payable", report_vars(as_of, books_from, company))


def group_summary_request(group: str, from_date: date, to_date: date, company: Optional[str] = None) -> str:
    """Tally's own Group Summary (top-level lines of `group`): the reference the per-ledger balances are
    checked against. Same variables, in the same order, as the Phase 0 request."""
    return _envelope_report("Group Summary", typed_dates(from_date, to_date) +
                            f"<GROUPNAME>{escape(group)}</GROUPNAME><EXPLODEFLAG>No</EXPLODEFLAG>" +
                            (f"<SVCURRENTCOMPANY>{escape(company)}</SVCURRENTCOMPANY>" if company else ""))


# ---------------------------------------------------------------------------
# Small parsers
# ---------------------------------------------------------------------------

def text(elem: Optional[ET.Element], tag: str) -> str:
    if elem is None:
        return ""
    v = elem.findtext(tag)
    return (v or "").strip()


def yes(elem: ET.Element, tag: str) -> bool:
    return text(elem, tag).lower() == "yes"


def amount(raw: Optional[str]) -> Optional[Decimal]:
    raw = (raw or "").strip().replace(",", "")
    if not raw:
        return None
    m = re.match(r"^(-?[\d.]+)", raw)  # "1234.00 Dr" forms are not used by collections, but be safe
    if not m:
        return None
    try:
        return Decimal(m.group(1))
    except InvalidOperation:
        return None


def ymd(raw: Optional[str]) -> Optional[str]:
    """Tally YYYYMMDD -> ISO, or None (never today's date)."""
    raw = (raw or "").strip()
    if re.fullmatch(r"\d{8}", raw):
        try:
            return datetime.strptime(raw, "%Y%m%d").date().isoformat()
        except ValueError:
            return None
    return None


def report_date(raw: Optional[str]) -> Optional[str]:
    """Report dates like '1-Apr-25' / '13-Nov-2026' -> ISO, or None."""
    raw = (raw or "").strip()
    for fmt in ("%d-%b-%y", "%d-%b-%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def aliases(led: ET.Element) -> List[str]:
    """Ledger aliases: every NAME after the first in LANGUAGENAME.LIST/NAME.LIST."""
    out: List[str] = []
    for lst in led.findall("./LANGUAGENAME.LIST/NAME.LIST"):
        names = [(n.text or "").strip() for n in lst.findall("NAME")]
        out.extend(n for n in names[1:] if n)
    return out


def element_name(e: ET.Element) -> str:
    return (e.attrib.get("NAME") or e.findtext("NAME") or "").strip()


def resolve_group_classes(groups: Iterable[ET.Element]) -> Dict[str, str]:
    """group name -> CASH | BANK | DEBTOR | OTHER, by walking parents to a reserved group."""
    parent: Dict[str, str] = {}
    reserved: Dict[str, str] = {}
    for g in groups:
        n = element_name(g)
        if not n:
            continue
        parent[n] = text(g, "PARENT")
        reserved[n] = (g.attrib.get("RESERVEDNAME") or "").strip()
    out: Dict[str, str] = {}
    for n in parent:
        cur, seen, cls = n, set(), "OTHER"
        while cur and cur not in seen:
            seen.add(cur)
            key = (reserved.get(cur) or cur).lower()
            if key in CASH_GROUPS:
                cls = "CASH"
                break
            if key in BANK_GROUPS:
                cls = "BANK"
                break
            if key == "sundry debtors":
                cls = "DEBTOR"
                break
            cur = parent.get(cur, "")
        out[n] = cls
    return out


def resolve_voucher_parents(types: Iterable[ET.Element]) -> Dict[str, str]:
    """voucher type name -> its base (reserved) type, following user-type chains."""
    parent = {element_name(t): text(t, "PARENT") for t in types if element_name(t)}
    out: Dict[str, str] = {}
    for n in parent:
        cur, seen = n, set()
        while parent.get(cur) and parent[cur] != cur and parent[cur] not in seen and parent[cur] in parent:
            seen.add(cur)
            cur = parent[cur]
        out[n] = parent.get(cur) or cur
    return out


def parse_bill(b: ET.Element) -> Optional[Dict[str, Any]]:
    amt = amount(text(b, "AMOUNT"))
    name = text(b, "NAME")
    btype = text(b, "BILLTYPE")
    if amt is None and not name and not btype:
        return None  # an empty <BILLALLOCATIONS.LIST> placeholder
    return {"name": name or None, "bill_type": btype or None, "amount": str(amt or Decimal("0")),
            "credit_period": text(b, "BILLCREDITPERIOD") or None}


def parse_bank(b: ET.Element) -> Optional[Dict[str, Any]]:
    fields = {
        "transaction_type": text(b, "TRANSACTIONTYPE") or None,
        "payment_mode": text(b, "PAYMENTMODE") or None,
        "instrument_number": text(b, "INSTRUMENTNUMBER") or None,
        "instrument_date": ymd(text(b, "INSTRUMENTDATE")),
        "unique_reference": text(b, "UNIQUEREFERENCENUMBER") or None,
        "bank_name": text(b, "BANKNAME") or None,
    }
    amt = amount(text(b, "AMOUNT"))
    if not any(fields.values()) and amt is None:
        return None
    fields["amount"] = str(amt) if amt is not None else None
    return {k: v for k, v in fields.items() if v is not None}
