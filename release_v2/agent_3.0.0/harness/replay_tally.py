"""ReplayTally - a TallyPrime stand-in that answers the agent's REAL requests from the RECORDED SGRG answers.

It subclasses the agent's own TallyClient and replaces only the HTTP transport (send_xml), so the agent's request
builders, company selection, XML cleaning and parsers all run unchanged.

RECORDED behaviour (from release_v2/agent_2.2.1/local_tally/raw_validate_*, the client's Tally copy of 18-Nov-2026):
  * the 37,715 vouchers (pruned to the lean fetch), their GUIDs, dates, types, ledger lines, bill / bank allocations
  * the masters: company, groups, all ledgers, voucher types, debtor ledgers (opening at 1-Apr-2025), creditors
  * Bills Receivable / Payable as of 18-Nov-2026
SIMULATED (by this harness, never by the recordings):
  * WHEN each voucher was entered: the k-th voucher by AlterID is entered on the date of the k-th voucher by date
    (09:00-19:00 IST, evenly) - so some are back-dated and some post-dated, as on the real books
  * AlterIDs are the recorded ones x 1000 (order preserved) so simulated edits fit between recorded entries
  * every injected event (new voucher, edit, deletion, cancellation, re-dating, new ledger, reallocation,
    credit / debit notes, Tally down / closed / slow)
  * balances: debtor opening / closing for any period = recorded opening at 1-Apr-2025 + movements of the vouchers
    visible now (non-cancelled, non-optional, accounting types); Group Summary = their sum
  * bills reports: the recorded 18-Nov-2026 bills dated on or before the requested as-of date
"""
from __future__ import annotations

import copy
import pickle
import re
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from tally_sync_agent.core.tally_client import TallyClient, TallyConnectionError

IST = timezone(timedelta(hours=5, minutes=30))
ALTER_SCALE = 1000
_MON = {m: i + 1 for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"))}
NON_ACCOUNTING = {p.lower() for p in (
    "Sales Order", "Purchase Order", "Delivery Note", "Receipt Note", "Rejections In", "Rejections Out",
    "Stock Journal", "Physical Stock", "Material In", "Material Out", "Job Work In Order", "Job Work Out Order",
    "Memorandum", "Reversing Journal", "Attendance")}
ENV_HEAD = ("<ENVELOPE><HEADER><VERSION>1</VERSION><STATUS>1</STATUS></HEADER><BODY><DESC><CMPINFO><VOUCHER>0</VOUCHER>"
            "</CMPINFO></DESC><DATA><COLLECTION>")
ENV_TAIL = "</COLLECTION></DATA></BODY></ENVELOPE>"


def tdate(s: str) -> date:
    """'13-Nov-2026' -> date."""
    d, m, y = s.strip().split("-")
    return date(int(y), _MON[m[:3].title()], int(d))


def bill_date(s: str) -> Optional[date]:
    """Report dates '1-Apr-25' / '13-Nov-2026'."""
    try:
        d, m, y = s.strip().split("-")
        y = int(y)
        return date(y + 2000 if y < 100 else y, _MON[m[:3].title()], int(d))
    except (ValueError, KeyError):
        return None


def money(s: Optional[str]) -> Decimal:
    s = (s or "").strip().replace(",", "")
    m = re.match(r"^-?[\d.]+", s)
    return Decimal(m.group(0)) if m else Decimal("0")


@dataclass
class Rec:
    guid: str
    date: date
    alter: int
    vtype: str
    xml: str
    entered_at: datetime
    recorded: bool = True
    deleted: bool = False
    history: List[str] = field(default_factory=list)   # simulated events applied

    def elem(self) -> ET.Element:
        return ET.fromstring(self.xml)


class ReplayTally(TallyClient):
    def __init__(self, store_path: str, company_guid: str = "19a03e17-e1ab-44f2-8e7f-1bff56f20ebe"):
        super().__init__(base_url="http://replay-tally.invalid:9000", timeout=1)
        with open(store_path, "rb") as f:
            store = pickle.load(f)
        self.masters_raw: Dict[str, str] = store["masters"]
        self.company_guid = company_guid
        self.now: datetime = datetime(2026, 4, 1, tzinfo=IST)
        self.down = False             # simulated: Tally not answering (connection refused / timeout)
        self.company_loaded = True    # simulated: Tally running but the company closed
        self.slow_seconds = 0.0       # simulated: a slow answer
        self.log: List[tuple] = []    # (kind, seconds, bytes, n_vouchers)
        self.max_alter = 0
        # ---------------------------------------------------------------- vouchers (recorded) + entry times (simulated)
        vs = store["vouchers"]                                  # sorted by recorded AlterID
        by_date = sorted(vs, key=lambda r: (r["date"], r["alter"]))
        per_day: Dict[str, int] = {}
        for r in by_date:
            per_day[r["date"]] = per_day.get(r["date"], 0) + 1
        seen_day: Dict[str, int] = {}
        self.recs: Dict[str, Rec] = {}
        for k, r in enumerate(vs):
            d = by_date[k]["date"]
            i = seen_day.get(d, 0)
            seen_day[d] = i + 1
            minutes = 9 * 60 + int(600 * (i + 0.5) / per_day[d])
            entered = datetime.fromisoformat(d).replace(tzinfo=IST) + timedelta(minutes=minutes)
            alter = r["alter"] * ALTER_SCALE
            xml = re.sub(r"<ALTERID>\s*\d+\s*</ALTERID>", f"<ALTERID>{alter}</ALTERID>", r["xml"], count=1)
            self.recs[r["guid"]] = Rec(r["guid"], date.fromisoformat(r["date"]), alter, r["vtype"], xml, entered)
            self.max_alter = max(self.max_alter, alter)
        # ---------------------------------------------------------------- masters (recorded)
        self.vtype_parent = self._voucher_parents(self.masters_raw["FtpVchTypes"])
        deb_root = self._root_of(self.masters_raw["FtpDebtors"])
        self.debtors: Dict[str, ET.Element] = {}
        self.opening0: Dict[str, Decimal] = {}
        for led in deb_root.iter("LEDGER"):
            if not len(led):
                continue
            name = (led.attrib.get("NAME") or led.findtext("NAME") or "").strip()
            if name:
                self.debtors[name.lower()] = led
                self.opening0[name.lower()] = money(led.findtext("OPENINGBALANCE"))
        self.extra_ledgers: List[str] = []   # simulated new ledgers (FtpLedgers additions)
        self._moves_cache: Dict[str, tuple] = {}

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _root_of(text: str) -> ET.Element:
        cleaned = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)
        return ET.fromstring(re.sub(r"<(/?)(\w+):", r"<\1\2_", cleaned))

    def _voucher_parents(self, raw: str) -> Dict[str, str]:
        parent = {}
        for vt in self._root_of(raw).iter("VOUCHERTYPE"):
            n = (vt.attrib.get("NAME") or "").strip()
            if n:
                parent[n] = (vt.findtext("PARENT") or "").strip()
        out = {}
        for n in parent:
            cur, hops = n, 0
            while parent.get(cur) and parent[cur] != cur and hops < 20:
                cur, hops = parent[cur], hops + 1
            out[n] = cur
        return out

    def visible(self) -> List[Rec]:
        return [r for r in self.recs.values() if not r.deleted and r.entered_at <= self.now]

    def parent_of(self, r: Rec) -> str:
        return self.vtype_parent.get(r.vtype, r.vtype)

    def moves(self, r: Rec) -> tuple:
        """(posts, [(debtor ledger lower, amount)], cancelled, optional) - parsed from the voucher XML."""
        key = f"{r.guid}:{r.alter}:{len(self.debtors)}"
        hit = self._moves_cache.get(key)
        if hit is not None:
            return hit
        e = r.elem()
        cancelled = (e.findtext("ISCANCELLED") or "").strip().lower() == "yes"
        optional = (e.findtext("ISOPTIONAL") or "").strip().lower() == "yes"
        posts = not cancelled and not optional and self.parent_of(r).lower() not in NON_ACCOUNTING
        lines = []
        for le in e.findall("ALLLEDGERENTRIES.LIST"):
            n = (le.findtext("LEDGERNAME") or "").strip().lower()
            if n in self.debtors:
                lines.append((n, money(le.findtext("AMOUNT"))))
        out = (posts, lines, cancelled, optional)
        self._moves_cache[key] = out
        return out

    def debtor_balances(self, pf: date, pt: date) -> Dict[str, tuple]:
        """ledger lower -> (opening at pf, closing at pt), Tally sign (negative = debit)."""
        before: Dict[str, Decimal] = {}
        during: Dict[str, Decimal] = {}
        fy0 = date(2025, 4, 1)
        for r in self.visible():
            if r.date < fy0 or r.date > pt:
                continue
            posts, lines, _, _ = self.moves(r)
            if not posts:
                continue
            tgt = before if r.date < pf else during
            for n, a in lines:
                tgt[n] = tgt.get(n, Decimal("0")) + a
        out = {}
        for n in self.debtors:
            o = self.opening0.get(n, Decimal("0")) + before.get(n, Decimal("0"))
            out[n] = (o, o + during.get(n, Decimal("0")))
        return out

    # ------------------------------------------------------------------ transport
    def send_xml(self, xml_payload: str) -> str:
        t0 = time.perf_counter()
        if self.down:
            raise TallyConnectionError("Could not connect to Tally at replay: [simulated] connection refused")
        if "<TALLYREQUEST>Export</TALLYREQUEST>" not in xml_payload:
            raise TallyConnectionError("replay Tally refuses anything but an Export")
        cid = (re.search(r"<ID>(.*?)</ID>", xml_payload) or [None, "?"])[1]
        sv = re.search(r'<SVFROMDATE TYPE="Date">(.*?)</SVFROMDATE><SVTODATE TYPE="Date">(.*?)</SVTODATE>', xml_payload)
        pf, pt = (tdate(sv.group(1)), tdate(sv.group(2))) if sv else (None, None)
        n = 0
        if cid == "CompanyCol":
            out = self.masters_raw["CompanyCol"] if self.company_loaded else ENV_HEAD + ENV_TAIL
        elif not self.company_loaded:
            out = ENV_HEAD + ENV_TAIL
        elif cid in ("FtpGroups", "FtpVchTypes", "FtpCreditors"):
            out = self.masters_raw[cid]
        elif cid == "FtpLedgers":
            out = self.masters_raw["FtpLedgers"]
            if self.extra_ledgers:
                i = out.rindex("</COLLECTION>")
                out = out[:i] + "".join(self.extra_ledgers) + out[i:]
        elif cid == "FtpDebtors":
            out = self._debtors(xml_payload, pf, pt)
        elif cid == "FtpVch":
            out, n = self._vouchers(xml_payload, pf, pt)
        elif cid == "Group Summary":
            bal = self.debtor_balances(pf, pt)
            net = sum((c for _, c in bal.values()), Decimal("0"))
            dr, cr = (f"{net:.2f}", "") if net < 0 else ("", f"{net:.2f}")
            out = (f"<ENVELOPE><DSPACCNAME><DSPDISPNAME>Sundry Debtors</DSPDISPNAME></DSPACCNAME><DSPACCINFO>"
                   f"<DSPCLDRAMT><DSPCLDRAMTA>{dr}</DSPCLDRAMTA></DSPCLDRAMT><DSPCLCRAMT><DSPCLCRAMTA>{cr}</DSPCLCRAMTA>"
                   f"</DSPCLCRAMT></DSPACCINFO></ENVELOPE>")
        elif cid in ("Bills Receivable", "Bills Payable"):
            out = self._bills(self.masters_raw[cid], pt)
        else:
            raise TallyConnectionError(f"replay Tally: unknown request {cid}")
        if self.slow_seconds:
            time.sleep(self.slow_seconds)
        self.log.append((cid, time.perf_counter() - t0, len(out), n))
        return self._clean_xml(out)

    def _debtors(self, xml: str, pf: date, pt: date) -> str:
        m = re.search(r"\$\$Number:\$AlterId &gt; (\d+)", xml)
        min_alter = int(m.group(1)) if m else None
        bal = self.debtor_balances(pf, pt)
        parts = []
        for n, led in self.debtors.items():
            a = (led.findtext("ALTERID") or "0").strip()
            if min_alter is not None and not (a.isdigit() and int(a) > min_alter):
                continue
            e = copy.deepcopy(led)
            o, c = bal[n]
            for tag, val in (("OPENINGBALANCE", o), ("CLOSINGBALANCE", c)):
                x = e.find(tag)
                if x is None:
                    x = ET.SubElement(e, tag)
                x.text = "" if val == 0 else f"{val:.2f}"
            parts.append(ET.tostring(e, encoding="unicode"))
        return ENV_HEAD + "".join(parts) + ENV_TAIL

    def _vouchers(self, xml: str, pf: date, pt: date) -> tuple:
        day = re.search(r'NAME="FtpDay">\$Date = \$\$Date:"(.*?)"', xml)
        rng = re.search(r'NAME="FtpRange">\$Date &gt;= \$\$Date:"(.*?)" AND \$Date &lt;= \$\$Date:"(.*?)"', xml)
        if day:
            a = b = tdate(day.group(1))
        elif rng:
            a, b = tdate(rng.group(1)), tdate(rng.group(2))
        else:
            raise TallyConnectionError("replay Tally: an unfiltered voucher request would never be answered here")
        assert (a, b) == (pf, pt), f"typed period {pf}..{pt} differs from the date filter {a}..{b}"
        m = re.search(r"\$\$Number:\$AlterId &gt; (\d+)", xml)
        min_alter = int(m.group(1)) if m else None
        headers_only = "VoucherNumber" not in (re.search(r"<FETCH>(.*?)</FETCH>", xml) or [None, ""])[1]
        sel = [r for r in self.visible() if a <= r.date <= b and (min_alter is None or r.alter > min_alter)]
        sel.sort(key=lambda r: (r.date, r.alter))
        if headers_only:
            body = "".join(self._header_xml(r) for r in sel)
        else:
            body = "".join(r.xml for r in sel)
        return ENV_HEAD + body + ENV_TAIL, len(sel)

    @staticmethod
    def _header_xml(r: Rec) -> str:
        e = r.elem()
        out = ET.Element("VOUCHER", dict(e.attrib))
        for tag in ("DATE", "GUID", "VOUCHERTYPENAME", "ISCANCELLED", "ISOPTIONAL", "ALTERID"):
            x = e.find(tag)
            if x is not None:
                ET.SubElement(out, tag).text = x.text
        return ET.tostring(out, encoding="unicode")

    def _bills(self, raw: str, as_of: date) -> str:
        root = self._root_of(raw)
        out, group, keep = [], [], True
        for child in list(root):
            if child.tag == "BILLFIXED":
                if group and keep:
                    out.extend(group)
                group = [child]
                bd = bill_date(child.findtext("BILLDATE") or "")
                keep = bd is not None and bd <= as_of
            else:
                group.append(child)
        if group and keep:
            out.extend(group)
        return "<ENVELOPE>" + "".join(ET.tostring(c, encoding="unicode") for c in out) + "</ENVELOPE>"

    # ------------------------------------------------------------------ simulated events
    def _next_alter(self) -> int:
        """Tally numbers every change company-wide: a simulated change gets the next number after everything entered so
        far, which stays below the next recorded entry (recorded AlterIDs are x1000)."""
        nxt = max([r.alter for r in self.recs.values() if r.entered_at <= self.now] + [0]) + 1
        if nxt % ALTER_SCALE == 0:
            raise RuntimeError("more than 999 simulated changes between two recorded entries")
        return nxt

    def _rewrite(self, r: Rec, e: ET.Element, event: str) -> None:
        r.alter = self._next_alter()
        e.find("ALTERID").text = str(r.alter)
        r.xml = ET.tostring(e, encoding="unicode")
        r.entered_at = min(r.entered_at, self.now)
        r.history.append(f"{self.now:%Y-%m-%d %H:%M} {event}")

    def edit_amount(self, guid: str, factor: Decimal) -> Rec:
        r = self.recs[guid]
        e = r.elem()
        for tag in e.iter():
            if tag.tag == "AMOUNT" and tag.text and money(tag.text) != 0:
                tag.text = f"{(money(tag.text) * factor).quantize(Decimal('0.01'))}"
        self._rewrite(r, e, f"amount x{factor}")
        return r

    def edit_narration(self, guid: str, text: str) -> Rec:
        r = self.recs[guid]
        e = r.elem()
        n = e.find("NARRATION")
        if n is None:
            n = ET.SubElement(e, "NARRATION")
        n.text = text
        self._rewrite(r, e, "narration")
        return r

    def cancel(self, guid: str) -> Rec:
        r = self.recs[guid]
        e = r.elem()
        e.find("ISCANCELLED").text = "Yes"
        self._rewrite(r, e, "cancelled")
        return r

    def delete(self, guid: str) -> Rec:
        r = self.recs[guid]
        r.deleted = True
        r.history.append(f"{self.now:%Y-%m-%d %H:%M} deleted")
        return r

    def redate(self, guid: str, new_date: date) -> Rec:
        r = self.recs[guid]
        e = r.elem()
        e.find("DATE").text = new_date.strftime("%Y%m%d")
        r.date = new_date
        self._rewrite(r, e, f"re-dated to {new_date}")
        return r

    def clone(self, template_guid: str, new_date: date, ledger: Optional[str] = None, factor: Decimal = Decimal("1"),
              number: Optional[str] = None, bill_name: Optional[str] = None) -> Rec:
        """A NEW voucher shaped like a recorded one (same type and lines), new GUID / date / number; optionally another
        debtor ledger, scaled amounts, a new bill name on its New Ref / Agst Ref allocations."""
        t = self.recs[template_guid]
        e = t.elem()
        g = f"{self.company_guid}-SIM{uuid.uuid4().hex[:12]}"
        e.find("GUID").text = g
        e.find("DATE").text = new_date.strftime("%Y%m%d")
        if number and e.find("VOUCHERNUMBER") is not None:
            e.find("VOUCHERNUMBER").text = number
        old_party = None
        for le in e.findall("ALLLEDGERENTRIES.LIST"):
            n = (le.findtext("LEDGERNAME") or "").strip()
            if ledger and n.lower() in self.debtors and old_party in (None, n):
                old_party = n
                le.find("LEDGERNAME").text = ledger
        if bill_name:   # a new invoice raises its OWN bill (Tally never makes two bills of one name per party)
            for le in e.findall("ALLLEDGERENTRIES.LIST"):
                if (le.findtext("LEDGERNAME") or "").strip().lower() in self.debtors or (ledger and
                        (le.findtext("LEDGERNAME") or "").strip() == ledger):
                    for b in le.findall("BILLALLOCATIONS.LIST"):
                        if b.find("NAME") is not None and (b.findtext("NAME") or "").strip():
                            b.find("NAME").text = bill_name
        if ledger and e.find("PARTYLEDGERNAME") is not None and old_party:
            e.find("PARTYLEDGERNAME").text = ledger
        for tag in e.iter():
            if tag.tag == "AMOUNT" and tag.text and money(tag.text) != 0 and factor != 1:
                tag.text = f"{(money(tag.text) * factor).quantize(Decimal('0.01'))}"
        r = Rec(g, new_date, 0, t.vtype, "", self.now, recorded=False)
        e.find("ALTERID").text = "0"
        self.recs[g] = r
        self._rewrite(r, e, f"created (shaped like recorded {t.vtype} {template_guid[-8:]})")
        return r

    def reallocate(self, receipt_guid: str, new_bill: str) -> Rec:
        """A receipt's Agst Ref allocations are moved to another bill of the same party (same totals)."""
        r = self.recs[receipt_guid]
        e = r.elem()
        for b in e.iter("BILLALLOCATIONS.LIST"):
            if (b.findtext("BILLTYPE") or "").strip().lower() == "agst ref" and b.find("NAME") is not None:
                b.find("NAME").text = new_bill
        self._rewrite(r, e, f"bills reallocated to {new_bill}")
        return r

    def add_debtor_ledger(self, template_name: str, new_name: str, parent: Optional[str] = None) -> str:
        """A NEW customer ledger under Sundry Debtors (masters + all-ledgers list), opening 0."""
        t = copy.deepcopy(self.debtors[template_name.lower()])
        t.attrib["NAME"] = new_name
        if t.find("NAME") is not None:
            t.find("NAME").text = new_name
        g = f"{self.company_guid}-SIMLED{uuid.uuid4().hex[:10]}"
        t.find("GUID").text = g
        alt = t.find("ALTERID")
        if alt is not None:
            alt.text = str(self._next_alter())
        for lang in t.iter("NAME.LIST"):
            for n in list(lang):
                lang.remove(n)
            ET.SubElement(lang, "NAME").text = new_name
        self.debtors[new_name.lower()] = t
        self.opening0[new_name.lower()] = Decimal("0")
        par = parent or (t.findtext("PARENT") or "Sundry Debtors")
        self.extra_ledgers.append(f'<LEDGER NAME="{new_name}"><PARENT>{par}</PARENT><GUID>{g}</GUID>'
                                  f"<LANGUAGENAME.LIST><NAME.LIST><NAME>{new_name}</NAME></NAME.LIST></LANGUAGENAME.LIST></LEDGER>")
        self._moves_cache.clear()
        return g
