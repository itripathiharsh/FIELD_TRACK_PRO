"""
Brand reconciliation: Tally vs FieldTrack (read-only).

How a brand reaches FieldTrack today
------------------------------------
FieldTrack does NOT receive Tally stock groups or stock items. The Tally agent derives ONE brand per debtor
ledger from (in order) the outlet code prefix, the ledger's PARENT GROUP name ("SUNDRY DEBTORS (OPPO)",
"Raunak ZBR", "Sundry Debtors- PH.") and the ledger name, using a fixed list of known brands. Every invoice
and receipt of that ledger then carries the ledger's brand. A ledger whose group / name names no known brand
(e.g. "Sandeep Jha", "Sunil Kumar", "Dharmendra (RR)", "Raunak Singer") arrives WITHOUT a brand, and so do
its invoices and receipts: they are reported here as "Unattributed".

A Tally group is never assumed to be a brand. A word in a group name that looks like a brand FieldTrack does
not know (see ``CANDIDATE_TOKENS``) is reported as "Tally brand not in FieldTrack - needs confirmation";
nothing is created or re-attributed automatically.
"""
from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.customer_brand import CustomerBrand
from app.models.invoice import Invoice, InvoiceSource
from app.models.payment import Payment, PaymentBrandAllocation, PaymentSource
from app.models.tally_debtor_ledger import TallyDebtorLedger
from app.services.brand_service import normalize_brand_name, resolve_canonical_brand_name
from app.services.report_filters import UNATTRIBUTED_BRAND

#: Words seen in Tally group names / voucher types that look like a brand FieldTrack has no master for.
#: Reported for confirmation only; never applied automatically.
CANDIDATE_TOKENS: dict[str, str] = {"rr": "RR", "singer": "Singer", "zebronic": "Zebronics"}
_TOKEN_RE = re.compile(r"[a-z]+")

STATUS_MATCHED = "MATCHED"
STATUS_TALLY_ONLY = "TALLY_BRAND_NOT_IN_FIELDTRACK"
STATUS_FIELDTRACK_ONLY = "FIELDTRACK_ONLY_NO_TALLY_RECORDS"
STATUS_UNATTRIBUTED = "UNATTRIBUTED_NO_BRAND_IN_TALLY"
STATUS_CANDIDATE = "POSSIBLE_TALLY_BRAND_NEEDS_CONFIRMATION"

ZERO = Decimal("0.00")


def candidate_brand(*names: Optional[str]) -> Optional[str]:
    """'Dharmendra (RR)' / 'RR Sales' -> 'RR'; 'Raunak Singer' -> 'Singer'; 'Sandeep Jha' -> None."""
    for n in names:
        for tok in _TOKEN_RE.findall((n or "").lower()):
            if tok in CANDIDATE_TOKENS:
                return CANDIDATE_TOKENS[tok]
    return None


def _canon(raw: Optional[str]) -> Optional[str]:
    if not raw or not raw.strip() or raw.strip().lower() == "general":
        return None
    return resolve_canonical_brand_name(raw)


async def brand_filter_options(session: AsyncSession) -> list[dict]:
    """The ACTIVE brands of the brand master (release 3.3: the admin-curated list), with how many Tally records
    each has, then 'Unattributed' when some records carry no brand. Inactive brands are not offered; their records
    still count in every total without a brand filter."""
    inv = dict((await session.execute(
        select(Invoice.brand, func.count()).where(Invoice.source == InvoiceSource.TALLY).group_by(Invoice.brand)
    )).all())
    pay = dict((await session.execute(
        select(PaymentBrandAllocation.brand, func.count()).group_by(PaymentBrandAllocation.brand)
    )).all())
    counts: dict[str, int] = defaultdict(int)
    for raw, n in list(inv.items()) + list(pay.items()):
        counts[normalize_brand_name(_canon(raw) or UNATTRIBUTED_BRAND)] += int(n)
    active = (await session.execute(select(Brand).where(Brand.is_active.is_(True)))).scalars().all()
    out = [{"name": b.name, "records": counts.get(b.normalized_name, 0), "unattributed": False} for b in active]
    out.sort(key=lambda r: (-r["records"], r["name"].lower()))
    un = counts.get(normalize_brand_name(UNATTRIBUTED_BRAND), 0)
    if un:
        out.append({"name": UNATTRIBUTED_BRAND, "records": un, "unattributed": True})
    return out


async def brand_reconciliation(session: AsyncSession) -> dict:
    """Rows of `Tally Brand | FieldTrack Brand | Status | Records` plus the unattributed Tally groups."""
    master = {normalize_brand_name(b.name): b for b in (await session.execute(select(Brand))).scalars().all()}

    stats: dict[str, dict] = defaultdict(lambda: {"ledgers": 0, "invoices": 0, "invoice_amount": ZERO,
                                                  "receipts": 0, "receipt_amount": ZERO, "outlets": 0})
    led_rows = (await session.execute(
        select(TallyDebtorLedger.brand_override, TallyDebtorLedger.brand_tally, func.count())
        .where(TallyDebtorLedger.is_debtor.is_(True))
        .group_by(TallyDebtorLedger.brand_override, TallyDebtorLedger.brand_tally)
    )).all()
    for over, tally, n in led_rows:
        b = _canon(over) or _canon(tally)
        if b:
            stats[b]["ledgers"] += int(n)
    for raw, n, amt in (await session.execute(
        select(Invoice.brand, func.count(), func.coalesce(func.sum(Invoice.amount), ZERO))
        .where(Invoice.source == InvoiceSource.TALLY).group_by(Invoice.brand)
    )).all():
        b = _canon(raw)
        if b:
            stats[b]["invoices"] += int(n)
            stats[b]["invoice_amount"] += amt
    for raw, n, amt in (await session.execute(
        select(PaymentBrandAllocation.brand, func.count(), func.coalesce(func.sum(PaymentBrandAllocation.allocated_amount), ZERO))
        .join(Payment, Payment.id == PaymentBrandAllocation.payment_id)
        .where(Payment.source == PaymentSource.TALLY).group_by(PaymentBrandAllocation.brand)
    )).all():
        b = _canon(raw)
        if b:
            stats[b]["receipts"] += int(n)
            stats[b]["receipt_amount"] += amt
    for raw, n in (await session.execute(
        select(CustomerBrand.brand, func.count(func.distinct(CustomerBrand.customer_id)))
        .where(CustomerBrand.is_active.is_(True)).group_by(CustomerBrand.brand)
    )).all():
        b = _canon(raw)
        if b:
            stats[b]["outlets"] += int(n)

    rows = []
    seen = set()
    for b, st in stats.items():
        key = normalize_brand_name(b)
        seen.add(key)
        m = master.get(key)
        has_tally = st["ledgers"] or st["invoices"] or st["receipts"]
        rows.append({
            "tally_brand": b if has_tally else None,
            "fieldtrack_brand": m.name if m else None,
            "fieldtrack_active": bool(m and m.is_active),
            "status": STATUS_MATCHED if (m and has_tally) else (STATUS_TALLY_ONLY if has_tally else STATUS_FIELDTRACK_ONLY),
            **st,
        })
    for key, m in master.items():
        if key not in seen:
            rows.append({"tally_brand": None, "fieldtrack_brand": m.name, "fieldtrack_active": bool(m.is_active),
                         "status": STATUS_FIELDTRACK_ONLY,
                         "ledgers": 0, "invoices": 0, "invoice_amount": ZERO, "receipts": 0,
                         "receipt_amount": ZERO, "outlets": 0})

    # Records Tally sends WITHOUT a brand, grouped by the ledger's parent group (and its sales voucher types).
    groups: dict[str, dict] = {}
    unbranded = (await session.execute(
        select(TallyDebtorLedger.id, TallyDebtorLedger.parent_group)
        .where(TallyDebtorLedger.is_debtor.is_(True),
               func.coalesce(func.trim(TallyDebtorLedger.brand_override), "") == "",
               func.coalesce(func.trim(TallyDebtorLedger.brand_tally), "") == "")
    )).all()
    led_group = {lid: (pg or "(no group)") for lid, pg in unbranded}
    for pg in led_group.values():
        g = groups.setdefault(pg, {"group": pg, "ledgers": 0, "invoices": 0, "invoice_amount": ZERO,
                                   "voucher_types": set()})
        g["ledgers"] += 1
    if led_group:
        for lid, vt, n, amt in (await session.execute(
            select(Invoice.tally_debtor_ledger_id, Invoice.tally_voucher_type, func.count(),
                   func.coalesce(func.sum(Invoice.amount), ZERO))
            .where(Invoice.source == InvoiceSource.TALLY, Invoice.tally_debtor_ledger_id.in_(list(led_group)))
            .group_by(Invoice.tally_debtor_ledger_id, Invoice.tally_voucher_type)
        )).all():
            g = groups[led_group[lid]]
            g["invoices"] += int(n)
            g["invoice_amount"] += amt
            if vt:
                g["voucher_types"].add(vt.strip())
    unattributed = []
    cand_totals: dict[str, dict] = {}
    for g in groups.values():
        cand = candidate_brand(g["group"], *sorted(g["voucher_types"]))
        unattributed.append({
            "group": g["group"], "ledgers": g["ledgers"], "invoices": g["invoices"],
            "invoice_amount": g["invoice_amount"], "voucher_types": sorted(g["voucher_types"]),
            "possible_brand": cand,
            "status": STATUS_CANDIDATE if cand else STATUS_UNATTRIBUTED,
        })
        if cand:
            c = cand_totals.setdefault(cand, {"ledgers": 0, "invoices": 0, "invoice_amount": ZERO})
            c["ledgers"] += g["ledgers"]
            c["invoices"] += g["invoices"]
            c["invoice_amount"] += g["invoice_amount"]
    unattributed.sort(key=lambda r: (-r["invoice_amount"], r["group"].lower()))
    for cand, c in cand_totals.items():
        m = master.get(normalize_brand_name(cand))
        rows.append({"tally_brand": f"{cand} (from group names; not sent as a brand)",
                     "fieldtrack_brand": m.name if m else None, "fieldtrack_active": bool(m and m.is_active),
                     "status": STATUS_CANDIDATE,
                     "ledgers": c["ledgers"], "invoices": c["invoices"], "invoice_amount": c["invoice_amount"],
                     "receipts": 0, "receipt_amount": ZERO, "outlets": 0})
    tot = {"ledgers": 0, "invoices": 0, "invoice_amount": ZERO}
    for g in unattributed:
        for k in tot:
            tot[k] += g[k]
    rows.append({"tally_brand": "(no brand in Tally)", "fieldtrack_brand": UNATTRIBUTED_BRAND, "fieldtrack_active": None,
                 "status": STATUS_UNATTRIBUTED, **tot, "receipts": 0, "receipt_amount": ZERO, "outlets": 0})
    order = {STATUS_MATCHED: 0, STATUS_TALLY_ONLY: 1, STATUS_CANDIDATE: 2, STATUS_UNATTRIBUTED: 3, STATUS_FIELDTRACK_ONLY: 4}
    rows.sort(key=lambda r: (order[r["status"]], -int(r["invoices"]), str(r["fieldtrack_brand"] or r["tally_brand"])))
    return {
        "source_note": (
            "FieldTrack receives no Tally stock groups or stock items. The brand of a record is the brand the Tally "
            "agent reads from the debtor ledger's parent group, outlet code or ledger name; ledgers whose names "
            "carry no known brand arrive without one (Unattributed)."
        ),
        "rows": rows,
        "unattributed_groups": unattributed,
    }
