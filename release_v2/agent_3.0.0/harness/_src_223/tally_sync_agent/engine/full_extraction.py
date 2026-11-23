"""
Full re-extraction from Tally, independent of AlterID checkpoints.

Pulls every customer ledger and every sales / receipt voucher dated from
settings.sync_from_date, validates them exactly like the incremental sync, and
writes a reconciliation report (aggregates only - no names, phones or amounts per
party) so the totals can be checked against Tally's own Sales and Receipt
registers before anything is uploaded.

It never reads or writes the incremental checkpoints, the quarantine or the retry
queue: the daemon's incremental state is untouched whether this runs as a dry run
or uploads. Uploads are idempotent on the backend (matched by Tally GUID).
"""
from __future__ import annotations

import json
import uuid
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from tally_sync_agent.config.settings import AGENT_VERSION, DATA_DIR, settings
from tally_sync_agent.core.logger import logger
from tally_sync_agent.transformers.normalizer import Normalizer
from tally_sync_agent.validators.data_validator import DataValidator

_TOL = 0.01


def _month(iso: Optional[str]) -> str:
    return (iso or "")[:7] or "unknown"


def _rejections(rejected: List[Dict[str, Any]]) -> Dict[str, int]:
    return dict(Counter((r.get("validation_error") or "unknown").split(":")[0] for r in rejected))


def _guid_dupes(items: List[Dict[str, Any]]) -> int:
    counts = Counter(i.get("source_reference") for i in items)
    return sum(1 for ref, n in counts.items() if ref and n > 1)


def summarize_customers(valid: List[Dict[str, Any]], rejected: List[Dict[str, Any]]) -> Dict[str, Any]:
    balances = [c["closing_balance"] for c in valid if c.get("closing_balance") is not None]
    openings = [c["opening_balance"] for c in valid if c.get("opening_balance") is not None]
    return {
        "with_opening_balance": sum(1 for o in openings if o != 0),
        "opening_balance_sum_signed": round(sum(openings), 2),
        "extracted": len(valid) + len(rejected),
        "valid": len(valid),
        "rejected": len(rejected),
        "rejected_by_reason": _rejections(rejected),
        "duplicate_guids": _guid_dupes(valid),
        "with_outlet_code": sum(1 for c in valid if c.get("outlet_code")),
        "with_phone": sum(1 for c in valid if c.get("contact_number")),
        "with_mobile": sum(1 for c in valid if c.get("mobile")),
        "with_email": sum(1 for c in valid if c.get("email")),
        "with_gstin": sum(1 for c in valid if c.get("gst_number")),
        "with_address": sum(1 for c in valid if c.get("address")),
        "with_zone": sum(1 for c in valid if c.get("zone")),
        "with_closing_balance": len(balances),
        "closing_balance_sum_signed": round(sum(balances), 2),
        "closing_balance_negative_count": sum(1 for b in balances if b < 0),
        "closing_balance_positive_count": sum(1 for b in balances if b > 0),
    }


def summarize_invoices(valid: List[Dict[str, Any]], rejected: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_month: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"count": 0, "amount": 0.0})
    for i in valid:
        m = by_month[_month(i.get("invoice_date"))]
        m["count"] += 1
        m["amount"] = round(m["amount"] + float(i.get("amount") or 0), 2)
    return {
        "extracted": len(valid) + len(rejected),
        "valid": len(valid),
        "rejected": len(rejected),
        "rejected_by_reason": _rejections(rejected),
        "duplicate_guids": _guid_dupes(valid),
        "amount_sum": round(sum(float(i.get("amount") or 0) for i in valid), 2),
        "with_due_date_from_tally": sum(1 for i in valid if i.get("due_date")),
        "without_due_date": sum(1 for i in valid if not i.get("due_date")),
        "with_bill_name": sum(1 for i in valid if i.get("bill_name")),
        "bill_name_differs_from_voucher_number": sum(
            1 for i in valid if i.get("bill_name") and i["bill_name"] != i.get("invoice_number")
        ),
        "with_outlet_code": sum(1 for i in valid if i.get("outlet_code")),
        "without_brand": sum(1 for i in valid if not i.get("brand")),
        "by_month": dict(sorted(by_month.items())),
    }


def summarize_payments(valid: List[Dict[str, Any]], rejected: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_month: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"count": 0, "amount": 0.0})
    by_bill_type: Dict[str, float] = defaultdict(float)
    allocated_sum = 0.0
    over_allocated = 0
    with_allocs = 0
    for p in valid:
        m = by_month[_month(p.get("payment_date"))]
        m["count"] += 1
        m["amount"] = round(m["amount"] + float(p.get("amount") or 0), 2)
        allocs = p.get("bill_allocations") or []
        if allocs:
            with_allocs += 1
        total = 0.0
        for a in allocs:
            amt = float(a.get("amount") or 0)
            total += amt
            by_bill_type[a.get("bill_type") or "UNSPECIFIED"] += amt
        allocated_sum += total
        if total - float(p.get("amount") or 0) > _TOL:
            over_allocated += 1
    return {
        "extracted": len(valid) + len(rejected),
        "valid": len(valid),
        "rejected": len(rejected),
        "rejected_by_reason": _rejections(rejected),
        "duplicate_guids": _guid_dupes(valid),
        "amount_sum": round(sum(float(p.get("amount") or 0) for p in valid), 2),
        "with_bill_allocations": with_allocs,
        "without_bill_allocations": len(valid) - with_allocs,
        "bill_allocated_sum": round(allocated_sum, 2),
        "bill_allocated_by_type": {k: round(v, 2) for k, v in sorted(by_bill_type.items())},
        "over_allocated_receipts": over_allocated,
        "payment_method_counts": dict(Counter(p.get("payment_method") or "UNKNOWN" for p in valid)),
        "by_month": dict(sorted(by_month.items())),
    }


def debtor_movement_check(report: Dict[str, Any]) -> Dict[str, Any]:
    """Indicative cross-check of debtor balances against the synced vouchers. Any
    difference points at debtor movements the sync does not carry (credit notes,
    sales returns, journals, debit notes) or sales to non-debtor parties."""
    c, i, p = report["customers"], report["invoices"], report["payments"]
    opening, closing = c["opening_balance_sum_signed"], c["closing_balance_sum_signed"]
    expected = round(opening - i["amount_sum"] + p["amount_sum"], 2)
    return {
        "assumption": "Tally exports receivable (debit) balances as negative amounts - confirm with inspect-ledgers",
        "opening_sum_signed": opening,
        "closing_sum_signed": closing,
        "sales_sum": i["amount_sum"],
        "receipts_sum": p["amount_sum"],
        "expected_closing_if_debit_negative": expected,
        "unexplained_difference": round(closing - expected, 2),
    }


def run_full_extraction(engine, upload: bool = False, report_dir: Optional[Path] = None) -> Dict[str, Any]:
    """`engine` is a SyncEngine (its Tally client, extractors and backend client are reused)."""
    started = datetime.now()
    to_date = started.strftime("%Y-%m-%d")
    report: Dict[str, Any] = {
        "mode": "UPLOAD" if upload else "DRY_RUN",
        "agent_version": AGENT_VERSION,
        "generated_at": started.isoformat(timespec="seconds"),
        "from_date": settings.sync_from_date,
        "to_date": to_date,
        "checkpoints_touched": False,
    }

    company = engine.tally.get_company_info()
    if not company or not company.get("name"):
        report["status"] = "NO_COMPANY_LOADED"
        return _write(report, report_dir)
    report["company_name"] = company["name"]
    report["company_guid"] = company.get("guid")
    # Ledger opening balances are as of BooksFrom: it must be 2026-04-01 for them to be
    # the 31-Mar-2026 opening balances.
    report["company_books_from"] = company.get("books_from")
    report["company_starting_date"] = company.get("starting_date")
    company_guid = company.get("guid")

    raw_c = engine.cust_extractor.extract_customers(min_alter_id=None)
    raw_i = engine.inv_extractor.extract_invoices(from_date=settings.sync_from_date, to_date=to_date, min_alter_id=None)
    raw_p = engine.pmt_extractor.extract_payments(from_date=settings.sync_from_date, to_date=to_date, min_alter_id=None)

    valid_c, rej_c = DataValidator.filter_valid("customers", [Normalizer.normalize_customer(c) for c in raw_c])
    valid_i, rej_i = DataValidator.filter_valid("invoices", [Normalizer.normalize_invoice(i) for i in raw_i])
    valid_p, rej_p = DataValidator.filter_valid("payments", [Normalizer.normalize_payment(p) for p in raw_p])

    report["customers"] = summarize_customers(valid_c, rej_c)
    report["invoices"] = summarize_invoices(valid_i, rej_i)
    report["payments"] = summarize_payments(valid_p, rej_p)
    report["debtor_movement_check"] = debtor_movement_check(report)

    if upload:
        report["upload"] = {
            "customers": _upload(engine, "customers", valid_c, company_guid),
            "invoices": _upload(engine, "invoices", valid_i, company_guid),
            "payments": _upload(engine, "payments", valid_p, company_guid),
        }
        failed = sum(u["failed_batches"] for u in report["upload"].values())
        report["status"] = "UPLOADED_WITH_FAILURES" if failed else "UPLOADED"
    else:
        report["status"] = "DRY_RUN_COMPLETE"
    report["duration_seconds"] = round((datetime.now() - started).total_seconds(), 2)
    manifest = {
        "generated_at": report["generated_at"],
        "company_guid": company_guid,
        "customers": sorted({c["source_reference"] for c in valid_c if c.get("source_reference")}),
        "invoices": sorted({i["source_reference"] for i in valid_i if i.get("source_reference")}),
        "payments": sorted({p["source_reference"] for p in valid_p if p.get("source_reference")}),
    }
    return _write(report, report_dir, manifest)


def _upload(engine, entity: str, items: List[Dict[str, Any]], company_guid: Optional[str]) -> Dict[str, Any]:
    """Customers first, then invoices, then payments (receipts settle invoices that must exist).
    A failed batch is reported, not queued: rerun the full extraction instead."""
    send = {"customers": engine.backend.sync_customers, "invoices": engine.backend.sync_invoices,
            "payments": engine.backend.sync_payments}[entity]
    out = {"batches": 0, "failed_batches": 0, "created": 0, "updated": 0, "item_failures": 0, "errors": []}
    for batch in engine._chunk_list(items, settings.batch_size):
        out["batches"] += 1
        try:
            res = send(str(uuid.uuid4()), company_guid, batch)
            out["created"] += res.get("created_count", 0)
            out["updated"] += res.get("updated_count", 0)
            out["item_failures"] += res.get("failed_count", 0)
            out["errors"].extend((e.get("error") or "")[:200] for e in (res.get("errors") or [])[:5])
        except Exception as ex:
            out["failed_batches"] += 1
            out["errors"].append(f"batch failed: {str(ex)[:200]}")
            logger.error(f"FULL_EXTRACTION_UPLOAD_FAILED entity={entity} error={ex}")
    out["errors"] = out["errors"][:20]
    return out


def _write(report: Dict[str, Any], report_dir: Optional[Path], manifest: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The report, plus (when extraction ran) a manifest of the Tally GUIDs seen - no
    names or amounts - used to find database records that do not exist in Tally."""
    target_dir = Path(report_dir or DATA_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    stem = f"full_extraction_{report['generated_at'].replace(':', '').replace('-', '')}"
    if manifest is not None:
        mpath = target_dir / f"{stem}_guids.json"
        mpath.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        report["guid_manifest_path"] = str(mpath)
    path = target_dir / f"{stem}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    report["report_path"] = str(path)
    logger.info(f"FULL_EXTRACTION_FINISHED status={report.get('status')} report={path}")
    return report
