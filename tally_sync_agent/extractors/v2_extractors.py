"""
Agent 2.0 extractors: masters (groups, ledgers, debtors, voucher types),
vouchers (debtor lines + counter-ledger classes), Bills Receivable, manifest.

Parsing is separated from fetching so the parsers run unchanged on the client's
real exported XML in tests. Nothing is invented: a voucher without a GUID or a
date is returned as a rejection with raw diagnostics, never given a key or
today's date.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from tally_sync_agent.extractors import tally_xml as tx
from tally_sync_agent.extractors.brand_resolver import BrandResolver
from tally_sync_agent.extractors.ledger_fields import DMS_REGEX, _first_text, parse_zone_and_area

# Alias forms proven as dealer codes on the client's ledgers (450 of 454 aliases).
OUTLET_CODE_PREFIXES = ("SGRGUS", "SGRGVU", "SGRGZBR", "UPDD", "EUPD", "INBC", "RT", "MH")


def outlet_code_from(aliases: List[str], name: str) -> Optional[str]:
    """Dealer code: an alias that looks like a code, else a code in the ledger name. Never invented."""
    for a in aliases:
        clean = a.strip().upper()
        if " " not in clean and any(clean.startswith(p) for p in OUTLET_CODE_PREFIXES) and any(ch.isdigit() for ch in clean):
            return clean[:50]
    m = DMS_REGEX.search(name or "")
    return m.group(1).upper() if m else None


# ---------------------------------------------------------------------------
# Masters
# ---------------------------------------------------------------------------

@dataclass
class Masters:
    group_class: Dict[str, str] = field(default_factory=dict)       # group -> CASH|BANK|DEBTOR|OTHER
    ledger_parent: Dict[str, str] = field(default_factory=dict)     # ledger name -> parent group
    ledger_guid: Dict[str, str] = field(default_factory=dict)       # ledger name -> guid
    ledger_aliases: Dict[str, List[str]] = field(default_factory=dict)
    debtors: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # debtor name (lower) -> ledger item
    voucher_parent: Dict[str, str] = field(default_factory=dict)    # voucher type -> base type

    def ledger_class(self, name: str) -> str:
        """Membership comes from the ledger's CURRENT group (all-ledger list + group tree,
        refreshed every cycle; equals Tally's CHILDOF Sundry Debtors set, 1,595 = 1,595 on
        the client's data); debtor details come from the debtor cache."""
        if name in self.ledger_parent:
            return self.group_class.get(self.ledger_parent[name], "OTHER")
        return "DEBTOR" if name.strip().lower() in self.debtors else "OTHER"

    def missing_debtor_details(self) -> List[str]:
        """Ledgers now under Sundry Debtors whose details are not cached yet (new / moved in)."""
        return [n for n, p in self.ledger_parent.items()
                if self.group_class.get(p) == "DEBTOR" and n.strip().lower() not in self.debtors]


def parse_debtor(led: ET.Element) -> Optional[Dict[str, Any]]:
    name = tx.element_name(led)
    guid = tx.text(led, "GUID")
    if not name or not guid:
        return None
    parent = tx.text(led, "PARENT")
    als = tx.aliases(led)
    address_lines = [n.text.strip() for n in led.findall(".//ADDRESS.LIST/ADDRESS") if n.text and n.text.strip()]
    code = outlet_code_from(als, name)
    zone, area = parse_zone_and_area(name, parent, address_lines)
    opening = tx.amount(tx.text(led, "OPENINGBALANCE"))
    closing = tx.amount(tx.text(led, "CLOSINGBALANCE"))
    alter = tx.text(led, "ALTERID")
    return {
        "guid": guid, "name": name, "parent": parent or None, "is_debtor": True, "aliases": als,
        "outlet_code": code,
        "brand": BrandResolver.resolve(parent_name=parent, ledger_name=name, outlet_code=code),
        "address": ", ".join(address_lines) or None,
        "state": _first_text(led, "STATENAME", ".//LEDMAILINGDETAILS.LIST/STATE") or None,
        "pincode": _first_text(led, "PINCODE", ".//LEDMAILINGDETAILS.LIST/PINCODE") or None,
        "gst_number": _first_text(led, "PARTYGSTIN", ".//LEDGSTREGDETAILS.LIST/GSTIN") or None,
        "contact_number": _first_text(led, "LEDGERPHONE") or None,
        "mobile": _first_text(led, "LEDGERMOBILE", "MOBILE") or None,
        "email": _first_text(led, "EMAIL") or None,
        "contact_person": _first_text(led, "LEDGERCONTACT") or None,
        "zone": zone, "area": area,
        "is_bill_wise": tx.yes(led, "ISBILLWISEON") if tx.text(led, "ISBILLWISEON") else None,
        "credit_period": tx.text(led, "BILLCREDITPERIOD") or None,
        # Blank = no balance / no entries this period: exactly zero, as Tally shows it.
        "opening_balance": str(opening) if opening is not None else "0",
        "closing_balance": str(closing) if closing is not None else "0",
        "alter_id": int(alter) if alter.isdigit() else None,
    }


def parse_masters(groups_root, ledgers_root, debtors_root, vtypes_root) -> Masters:
    m = Masters()
    m.group_class = tx.resolve_group_classes(groups_root.iter("GROUP"))
    for led in ledgers_root.iter("LEDGER"):
        n = tx.element_name(led)
        if n:
            m.ledger_parent[n] = tx.text(led, "PARENT")
            m.ledger_guid[n] = tx.text(led, "GUID")
            m.ledger_aliases[n] = tx.aliases(led)
    for led in debtors_root.iter("LEDGER"):
        item = parse_debtor(led)
        if item:
            m.debtors[item["name"].lower()] = item
    m.voucher_parent = tx.resolve_voucher_parents(vtypes_root.iter("VOUCHERTYPE"))
    return m


def ledger_snapshot_items(m: Masters) -> List[Dict[str, Any]]:
    """Every ledger: debtors in full, others as GUID + group only (to mark non-debtors)."""
    items = []
    for name, guid in m.ledger_guid.items():
        if not guid:
            continue
        d = m.debtors.get(name.strip().lower())
        if m.ledger_class(name) == "DEBTOR" and d is not None:
            items.append(d)
        elif m.ledger_class(name) != "DEBTOR":
            items.append({"guid": guid, "name": name, "parent": m.ledger_parent.get(name) or None,
                          "is_debtor": False, "aliases": m.ledger_aliases.get(name, [])})
    return items


# ---------------------------------------------------------------------------
# Vouchers
# ---------------------------------------------------------------------------

def _entries(v: ET.Element) -> List[ET.Element]:
    lines = v.findall("./ALLLEDGERENTRIES.LIST")
    return lines or v.findall("./LEDGERENTRIES.LIST")


def parse_voucher(v: ET.Element, m: Masters) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """-> (voucher payload, None) or (None, rejection)."""
    guid = tx.text(v, "GUID")
    iso = tx.ymd(tx.text(v, "DATE"))
    vtype = tx.text(v, "VOUCHERTYPENAME") or v.attrib.get("VCHTYPE", "").strip()
    alter = tx.text(v, "ALTERID")
    alter_id = int(alter) if alter.isdigit() else None
    if not guid or not iso or not vtype:
        return None, {
            "source_reference": guid or None, "alter_id": alter_id,
            "validation_error": "missing " + ", ".join(k for k, ok in (("GUID", guid), ("date", iso), ("voucher type", vtype)) if not ok),
            "raw": {"date": tx.text(v, "DATE"), "type": vtype, "number": tx.text(v, "VOUCHERNUMBER"),
                    "party": tx.text(v, "PARTYLEDGERNAME"), "amount": tx.text(v, "AMOUNT")},
        }
    debtor_lines, counter_lines = [], []
    for e in _entries(v):
        name = tx.text(e, "LEDGERNAME")
        amt = tx.amount(tx.text(e, "AMOUNT"))
        if not name or amt is None:
            continue
        bills = [b for b in (tx.parse_bill(x) for x in e.findall("./BILLALLOCATIONS.LIST")) if b]
        banks = [b for b in (tx.parse_bank(x) for x in e.findall("./BANKALLOCATIONS.LIST")) if b]
        cls = m.ledger_class(name)
        d = m.debtors.get(name.strip().lower()) if cls == "DEBTOR" else None
        if cls == "DEBTOR" and d is None:
            return None, {"source_reference": guid, "alter_id": alter_id,
                          "validation_error": f"debtor ledger '{name}' has no cached details yet",
                          "raw": {"date": iso, "type": vtype}}
        if cls == "DEBTOR":
            debtor_lines.append({"ledger_name": name, "ledger_guid": d["guid"], "amount": str(amt),
                                 "brand": d.get("brand"), "bill_allocations": bills, "bank_allocations": banks})
        else:
            counter_lines.append({"ledger_name": name, "ledger_class": cls, "amount": str(amt),
                                  "bank_allocations": banks})
    payload = {
        "guid": guid, "alter_id": alter_id, "date": iso, "voucher_type": vtype,
        "voucher_parent": m.voucher_parent.get(vtype) or None,
        "voucher_number": tx.text(v, "VOUCHERNUMBER") or None,
        "party_ledger": tx.text(v, "PARTYLEDGERNAME") or None,
        "narration": tx.text(v, "NARRATION") or None,
        "is_cancelled": tx.yes(v, "ISCANCELLED"), "is_optional": tx.yes(v, "ISOPTIONAL"),
        "debtor_lines": debtor_lines,
        # Counter lines only matter for receipts' payment mode: keep them small.
        "counter_lines": counter_lines if debtor_lines else [],
    }
    return payload, None


def voucher_elements(root: ET.Element) -> Iterable[ET.Element]:
    """Voucher objects only: Tally also emits scalar <VOUCHER>0</VOUCHER> fields inside sub-lists."""
    return (v for v in root.iter("VOUCHER") if len(v))


def parse_vouchers(root: ET.Element, m: Masters) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    good, bad = [], []
    for v in voucher_elements(root):
        p, r = parse_voucher(v, m)
        (good if p else bad).append(p or r)
    return good, bad


def parse_manifest(root: ET.Element) -> Tuple[List[str], int]:
    """(GUIDs, max AlterID) of a header-only voucher export."""
    guids, max_alter = [], 0
    for v in voucher_elements(root):
        g = tx.text(v, "GUID")
        if g:
            guids.append(g)
        a = tx.text(v, "ALTERID")
        if a.isdigit():
            max_alter = max(max_alter, int(a))
    return guids, max_alter


def parse_manifest_entries(root: ET.Element) -> List[Tuple[str, str, int]]:
    """(GUID, DATE as Tally's YYYYMMDD or "", AlterID or 0) per voucher with a GUID.
    Same voucher rule and same GUIDs as parse_manifest; the date lets the range scan
    prove that Tally honoured the requested window."""
    out = []
    for v in voucher_elements(root):
        g = tx.text(v, "GUID")
        if not g:
            continue
        a = tx.text(v, "ALTERID")
        out.append((g, tx.text(v, "DATE"), int(a) if a.isdigit() else 0))
    return out


def line_error(root: ET.Element) -> str:
    """Tally's LINEERROR text (a rejected request), or ""."""
    return " ".join((e.text or "").strip() for e in root.iter("LINEERROR")).strip()


# ---------------------------------------------------------------------------
# Bills Receivable report
# ---------------------------------------------------------------------------

def parse_bills_receivable(root: ET.Element, m: Optional[Masters] = None) -> List[Dict[str, Any]]:
    """BILLFIXED(BILLDATE, BILLREF, BILLPARTY), BILLFIXED1..5, BILLCL, BILLDUE, BILLOVERDUE
    repeat in document order. Only debtor ledgers' bills are returned when masters are given."""
    bills: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    for child in list(root):
        t = child.tag
        if t == "BILLFIXED":
            cur = {"bill_date": tx.report_date(tx.text(child, "BILLDATE")),
                   "bill_name": tx.text(child, "BILLREF"), "ledger_name": tx.text(child, "BILLPARTY")}
            bills.append(cur)
        elif cur is None:
            continue
        elif t == "BILLCL":
            amt = tx.amount(child.text)
            cur["pending_amount"] = str(amt) if amt is not None else None
        elif t == "BILLDUE":
            cur["due_date"] = tx.report_date(child.text)
        elif t == "BILLOVERDUE":
            raw = (child.text or "").strip()
            cur["overdue_days"] = int(raw) if raw.lstrip("-").isdigit() else None
    out = []
    for b in bills:
        if not b.get("bill_name") or not b.get("ledger_name") or b.get("pending_amount") is None:
            continue
        if m is not None:
            d = m.debtors.get(b["ledger_name"].strip().lower())
            if d is None:
                continue
            b["ledger_guid"] = d["guid"]
        out.append(b)
    return out


# ---------------------------------------------------------------------------
# 2.2.0: Group Summary, plain ledger balances, any bills report
# ---------------------------------------------------------------------------

def parse_group_summary_net(root: ET.Element) -> Decimal:
    """Net closing of a Group Summary report: sum of every top-level DSPCLDRAMTA (debit, negative)
    and DSPCLCRAMTA (credit, positive) line. An empty report (<ENVELOPE></ENVELOPE>) is 0.
    Proven on Phase 0: equals the per-ledger closing sums to the paisa in FY 2025-26 and 2026-27."""
    total = Decimal("0")
    for tag in ("DSPCLDRAMTA", "DSPCLCRAMTA"):
        for e in root.iter(tag):
            amt = tx.amount(e.text)
            if amt is not None:
                total += amt
    return total


def parse_ledger_balances(root: ET.Element) -> Dict[str, Dict[str, Any]]:
    """name.lower() -> {name, guid, parent, opening, closing (Decimal; blank = 0), closing_blank}.
    A blank balance is Tally's zero (it omits zero values); the Group Summary check proves it."""
    out: Dict[str, Dict[str, Any]] = {}
    for led in root.iter("LEDGER"):
        if not len(led):
            continue
        name = (led.attrib.get("NAME") or tx.text(led, "NAME")).strip()
        if not name:
            continue
        o = tx.amount(tx.text(led, "OPENINGBALANCE"))
        c_raw = tx.text(led, "CLOSINGBALANCE")
        c = tx.amount(c_raw)
        out[name.lower()] = {"name": name, "guid": tx.text(led, "GUID") or None, "parent": tx.text(led, "PARENT") or None,
                             "opening": o if o is not None else Decimal("0"), "closing": c if c is not None else Decimal("0"),
                             "closing_blank": not (c_raw or "").strip()}
    return out


def parse_bills_any(root: ET.Element, parties: Optional[set] = None) -> List[Dict[str, Any]]:
    """Every bill of a Bills Receivable / Bills Payable report; only `parties` (lower-case names) when given."""
    out = []
    for b in parse_bills_receivable(root, None):
        if parties is not None and b["ledger_name"].strip().lower() not in parties:
            continue
        out.append(b)
    return out
