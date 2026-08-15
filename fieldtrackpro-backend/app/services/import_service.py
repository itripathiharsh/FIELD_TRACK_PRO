"""
Import Service: the full Excel/MIS import pipeline.

Upload -> Parse -> Map -> Validate -> Preview -> Admin confirms -> Transactional
commit -> Success summary, per the P1 spec. Two DB-touching entry points:

  create_import_batch(...)  - read-only against the business tables. Parses
                               the FULL file, resolves every row's Territory/
                               Employee/Customer/Invoice/Payment identity
                               against what already exists, validates, and
                               persists the fully-resolved plan (not yet
                               applied) as an ImportBatch(status=VALIDATED).

  commit_import_batch(...)  - the only place that writes to
                               territories/employees/customers/invoices/
                               payments. Runs the stored plan inside one
                               transaction; any unexpected failure rolls the
                               whole batch back and marks it FAILED.

No column names are hardcoded from a guessed client file - TARGET_FIELDS is
the fixed set of things FieldTrack can receive; which Excel column maps to
which target field is a per-import, admin-controlled choice.
"""
from __future__ import annotations

import io
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import openpyxl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import BaseAPIException
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.import_batch import ImportBatch, ImportStatus
from app.models.invoice import Invoice, InvoiceSource
from app.models.payment import Payment, PaymentMethod, PaymentSource, PaymentStatus
from app.models.territory import Territory
from app.models.user import User

MAX_PREVIEW_ROWS = 20
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024

# ---------------------------------------------------------------------------
# Target field registry - the fixed, reviewable set of things an Excel
# column can be mapped to. Adding a client-specific column meaning here
# would be inventing the client's schema; this list only names concepts
# FieldTrack's own data model already has (Employee, Territory, Customer,
# Invoice, Payment).
# ---------------------------------------------------------------------------

TARGET_FIELDS: dict[str, dict[str, Any]] = {
    "territory_name":               {"label": "Territory Name",            "required": False, "aliases": ["territory", "area", "region", "zone", "town"]},
    "employee_code":                {"label": "Employee Code",             "required": False, "aliases": ["employee code", "emp code", "emp id", "fos code", "salesperson code"]},
    "employee_name":                {"label": "Employee Name",             "required": False, "aliases": ["employee", "employee name", "salesperson", "fos", "rep name", "sales rep"]},
    "outlet_code":                  {"label": "Outlet Code",               "required": False, "aliases": ["outlet code", "outlet id", "customer id", "retailer code", "client id"]},
    "outlet_name":                  {"label": "Outlet Name",               "required": False, "aliases": ["outlet", "outlet name", "retailer", "retailer name", "customer name", "shop name"]},
    "outlet_address":               {"label": "Outlet Address",            "required": False, "aliases": ["address", "outlet address", "shop address", "location"]},
    "outlet_contact_number":        {"label": "Outlet Contact Number",     "required": False, "aliases": ["contact", "phone", "mobile", "contact number"]},
    "outlet_latitude":              {"label": "Outlet Latitude",           "required": False, "aliases": ["latitude", "lat"]},
    "outlet_longitude":             {"label": "Outlet Longitude",          "required": False, "aliases": ["longitude", "lng", "long"]},
    "invoice_number":               {"label": "Invoice Number",            "required": False, "aliases": ["invoice no", "invoice number", "bill no", "voucher no"]},
    "invoice_date":                 {"label": "Invoice Date",              "required": False, "aliases": ["invoice date", "bill date", "voucher date"]},
    "invoice_amount":               {"label": "Invoice Amount",            "required": False, "aliases": ["invoice amount", "bill amount", "amount"]},
    "invoice_due_date":             {"label": "Invoice Due Date",          "required": False, "aliases": ["due date"]},
    "invoice_brand":                {"label": "Brand",                    "required": False, "aliases": ["brand", "brand name"]},
    "invoice_outstanding_reported": {"label": "Outstanding (as reported)", "required": False, "aliases": ["outstanding", "balance", "remaining", "due amount"]},
    "payment_amount":               {"label": "Payment Amount",            "required": False, "aliases": ["payment amount", "paid amount", "collection amount", "received amount"]},
    "payment_date":                 {"label": "Payment Date",              "required": False, "aliases": ["payment date", "collection date", "received date"]},
    "payment_method":               {"label": "Payment Method",            "required": False, "aliases": ["payment method", "mode", "payment mode"]},
    "payment_reference":            {"label": "Payment Reference / UTR / Cheque No", "required": False, "aliases": ["utr", "reference", "cheque no", "cheque number", "ref no"]},
}

OUTLET_STRATEGY_CODE = "outlet_code"
OUTLET_STRATEGY_NAME_TERRITORY = "name_and_territory"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def suggest_column_mapping(columns: list[str]) -> dict[str, Optional[str]]:
    """
    Heuristic auto-mapping: normalize each detected column header and match
    it against TARGET_FIELDS' known aliases. Never guesses ambiguously - an
    unmatched column maps to None ("ignored") and the admin can still assign
    it manually.
    """
    suggestion: dict[str, Optional[str]] = {}
    used_targets: set[str] = set()
    for col in columns:
        norm = _normalize(col)
        matched_key = None
        for key, spec in TARGET_FIELDS.items():
            if key in used_targets:
                continue
            names = [key.replace("_", " ")] + spec["aliases"]
            if norm in (_normalize(n) for n in names):
                matched_key = key
                break
        if matched_key:
            used_targets.add(matched_key)
        suggestion[col] = matched_key
    return suggestion


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def list_sheet_names(file_bytes: bytes) -> list[str]:
    workbook = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    names = workbook.sheetnames
    workbook.close()
    return names


def preview_excel_file(file_bytes: bytes, filename: str, sheet_name: str | None = None) -> dict:
    """Column-agnostic sample preview (unchanged contract from the original P1 pass)."""
    _validate_upload(file_bytes, filename)
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        sheet = workbook[sheet_name] if sheet_name else workbook.active
    except Exception as err:
        raise BaseAPIException(status_code=400, detail=f"Could not read the file as an Excel workbook: {err}", error_code="IMPORT_UNREADABLE_FILE")

    rows_iter = sheet.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        raise BaseAPIException(status_code=400, detail="The file has no rows", error_code="IMPORT_NO_ROWS")

    columns = [str(c).strip() if c is not None else f"(blank column {i + 1})" for i, c in enumerate(header_row)]
    sample_rows: list[list[str]] = []
    total_data_rows = 0
    for row in rows_iter:
        total_data_rows += 1
        if len(sample_rows) < MAX_PREVIEW_ROWS:
            sample_rows.append([("" if c is None else str(c)) for c in row])
    all_sheets = workbook.sheetnames
    workbook.close()

    return {
        "sheet_name": sheet.title,
        "all_sheets": all_sheets,
        "columns": columns,
        "sample_rows": sample_rows,
        "total_data_rows": total_data_rows,
        "truncated": total_data_rows > MAX_PREVIEW_ROWS,
        "suggested_mapping": suggest_column_mapping(columns),
        "target_fields": TARGET_FIELDS,
    }


def _validate_upload(file_bytes: bytes, filename: str) -> None:
    if len(file_bytes) == 0:
        raise BaseAPIException(status_code=400, detail="Uploaded file is empty", error_code="IMPORT_FILE_EMPTY")
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise BaseAPIException(status_code=400, detail=f"File exceeds the {MAX_FILE_SIZE_BYTES // (1024*1024)}MB limit", error_code="IMPORT_FILE_TOO_LARGE")
    if not filename.lower().endswith((".xlsx", ".xlsm")):
        raise BaseAPIException(status_code=415, detail="Only .xlsx/.xlsm files are supported", error_code="IMPORT_UNSUPPORTED_FORMAT")


def _parse_full_sheet(file_bytes: bytes, sheet_name: str) -> tuple[list[str], list[list[Any]]]:
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        sheet = workbook[sheet_name]
    except KeyError:
        raise BaseAPIException(status_code=400, detail=f"Sheet '{sheet_name}' not found", error_code="IMPORT_SHEET_NOT_FOUND")
    except Exception as err:
        raise BaseAPIException(status_code=400, detail=f"Could not read the file: {err}", error_code="IMPORT_UNREADABLE_FILE")

    rows_iter = sheet.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        raise BaseAPIException(status_code=400, detail="The file has no rows", error_code="IMPORT_NO_ROWS")
    columns = [str(c).strip() if c is not None else f"(blank column {i + 1})" for i, c in enumerate(header_row)]

    data_rows = []
    for row in rows_iter:
        if all(c is None for c in row):
            continue  # skip fully blank rows rather than treating them as data
        data_rows.append(list(row))
    workbook.close()
    return columns, data_rows


# ---------------------------------------------------------------------------
# Value coercion helpers - never raise; return (value, error_message_or_None)
# ---------------------------------------------------------------------------

def _coerce_date(raw: Any) -> tuple[Optional[date], Optional[str]]:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, None
    if isinstance(raw, datetime):
        return raw.date(), None
    if isinstance(raw, date):
        return raw, None
    text = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%d %b %Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(text, fmt).date(), None
        except ValueError:
            continue
    return None, f"Could not parse '{text}' as a date"


def _coerce_amount(raw: Any) -> tuple[Optional[Decimal], Optional[str]]:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, None
    if isinstance(raw, (int, float, Decimal)):
        try:
            return Decimal(str(raw)), None
        except InvalidOperation:
            return None, f"Could not parse '{raw}' as a number"
    text = str(raw).strip().replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "").strip()
    try:
        return Decimal(text), None
    except InvalidOperation:
        return None, f"Could not parse '{raw}' as a number"


def _text(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


# ---------------------------------------------------------------------------
# Batch-wide lookup context (avoids one query per row)
# ---------------------------------------------------------------------------

@dataclass
class ImportContext:
    territories_by_name: dict[str, uuid.UUID] = field(default_factory=dict)
    employees_by_code: dict[str, uuid.UUID] = field(default_factory=dict)
    employees_by_name: dict[str, list[uuid.UUID]] = field(default_factory=dict)
    customers_by_outlet_code: dict[str, uuid.UUID] = field(default_factory=dict)
    customers_by_name_territory: dict[tuple[str, str], list[uuid.UUID]] = field(default_factory=dict)
    invoices_by_customer_number: dict[tuple[str, str], uuid.UUID] = field(default_factory=dict)
    payments_by_customer_reference: dict[tuple[str, str], uuid.UUID] = field(default_factory=dict)
    # Names/codes newly introduced by earlier rows *within this same batch*,
    # so row 50 referencing the same new territory as row 3 reuses one plan,
    # not two.
    pending_territories: dict[str, str] = field(default_factory=dict)  # normalized_name -> original_name
    pending_customers: dict[str, dict] = field(default_factory=dict)  # outlet_code -> planned customer data


async def _build_context(session: AsyncSession) -> ImportContext:
    ctx = ImportContext()

    result = await session.execute(select(Territory.id, Territory.name))
    for tid, name in result.all():
        ctx.territories_by_name[_normalize(name)] = tid

    result = await session.execute(select(Employee.id, Employee.employee_code, Employee.full_name))
    for eid, code, name in result.all():
        if code:
            ctx.employees_by_code[_normalize(code)] = eid
        ctx.employees_by_name.setdefault(_normalize(name), []).append(eid)

    result = await session.execute(select(Customer.id, Customer.outlet_code, Customer.name, Customer.territory_id))
    territory_names_by_id = {v: k for k, v in ctx.territories_by_name.items()}
    for cid, outlet_code, name, territory_id in result.all():
        if outlet_code:
            ctx.customers_by_outlet_code[_normalize(outlet_code)] = cid
        territory_key = territory_names_by_id.get(territory_id, "")
        ctx.customers_by_name_territory.setdefault((_normalize(name), territory_key), []).append(cid)

    result = await session.execute(select(Invoice.customer_id, Invoice.invoice_number, Invoice.id))
    for cid, number, iid in result.all():
        ctx.invoices_by_customer_number[(str(cid), _normalize(number))] = iid

    result = await session.execute(
        select(Payment.customer_id, Payment.source_reference, Payment.id).where(Payment.source_reference.is_not(None))
    )
    for cid, ref, pid in result.all():
        ctx.payments_by_customer_reference[(str(cid), ref)] = pid

    return ctx


# ---------------------------------------------------------------------------
# Per-row resolution
# ---------------------------------------------------------------------------

def _resolve_territory(mapped: dict[str, Any], ctx: ImportContext) -> tuple[Optional[str], Optional[str], list[str]]:
    """Returns (territory_key_for_plan, territory_name, warnings). territory_key
    is either an existing id (as str) or a 'NEW:<normalized name>' plan marker."""
    name = _text(mapped.get("territory_name"))
    if not name:
        return None, None, []
    norm = _normalize(name)
    if norm in ctx.territories_by_name:
        return str(ctx.territories_by_name[norm]), name, []
    ctx.pending_territories[norm] = name
    return f"NEW:{norm}", name, []


def _resolve_employee(mapped: dict[str, Any], ctx: ImportContext) -> tuple[Optional[str], list[str], list[str]]:
    """
    Returns (employee_id_as_str_or_None, errors, warnings).

    Never returns a blocking error itself: an unresolved employee only
    matters if something on this row actually needs it (currently: a
    payment). Blocking on it unconditionally would silently drop an
    otherwise-perfectly-importable invoice on a row that merely also
    happened to carry an employee-attribution column. The payment-plan
    logic in create_import_batch is the one place that promotes this to a
    row error, exactly when a payment on that row requires it.
    """
    code = _text(mapped.get("employee_code"))
    name = _text(mapped.get("employee_name"))
    if code:
        eid = ctx.employees_by_code.get(_normalize(code))
        if eid:
            return str(eid), [], []
        return None, [], [f"No employee found with employee_code '{code}'"]
    if name:
        candidates = ctx.employees_by_name.get(_normalize(name), [])
        if len(candidates) == 1:
            return str(candidates[0]), [], []
        if len(candidates) > 1:
            return None, [], [f"Ambiguous employee name '{name}' matches {len(candidates)} employees - use employee_code instead or resolve manually"]
        return None, [], [f"No employee found with name '{name}'"]
    return None, [], []


def _resolve_outlet(
    mapped: dict[str, Any], ctx: ImportContext, strategy: str, territory_key: Optional[str], territory_name: Optional[str]
) -> tuple[Optional[str], str, list[str], list[str]]:
    """
    Returns (customer_key, action, errors, warnings). customer_key is either
    an existing id (str), a 'NEW:<outlet_code>' plan marker, or None if
    unresolved. action is one of MATCH/CREATE/UNRESOLVED.
    """
    errors: list[str] = []
    warnings: list[str] = []
    outlet_code = _text(mapped.get("outlet_code"))
    outlet_name = _text(mapped.get("outlet_name"))
    lat_raw = mapped.get("outlet_latitude")
    lng_raw = mapped.get("outlet_longitude")
    contact = _text(mapped.get("outlet_contact_number"))

    if strategy == OUTLET_STRATEGY_CODE:
        if not outlet_code:
            errors.append("No outlet_code provided for this row, and the batch is configured to match outlets by code")
            return None, "UNRESOLVED", errors, warnings
        norm = _normalize(outlet_code)
        existing = ctx.customers_by_outlet_code.get(norm)
        if existing:
            return str(existing), "MATCH", errors, warnings
        if norm in ctx.pending_customers:
            return f"NEW:{norm}", "CREATE", errors, warnings
        # New outlet - needs enough data to actually create a Customer row.
        if not outlet_name:
            errors.append(f"Outlet code '{outlet_code}' does not exist yet and no outlet_name was provided to create it")
            return None, "UNRESOLVED", errors, warnings
        lat, lat_err = _coerce_amount(lat_raw)
        lng, lng_err = _coerce_amount(lng_raw)
        if lat is None or lng is None:
            warnings.append(
                f"Outlet '{outlet_name}' ({outlet_code}) has no coordinates in the source file - "
                "cannot safely create it with a fabricated location (geofence check-in depends on it). "
                "Create this outlet manually with real coordinates, then re-import."
            )
            return None, "UNRESOLVED", errors, warnings
        if not contact:
            warnings.append(f"Outlet '{outlet_name}' ({outlet_code}) has no contact number - cannot create it (required field)")
            return None, "UNRESOLVED", errors, warnings
        ctx.pending_customers[norm] = {
            "outlet_code": outlet_code, "name": outlet_name, "latitude": float(lat), "longitude": float(lng),
            "contact_number": contact, "territory_key": territory_key,
            "address": _text(mapped.get("outlet_address")) or outlet_name,
        }
        return f"NEW:{norm}", "CREATE", errors, warnings

    # OUTLET_STRATEGY_NAME_TERRITORY
    if not outlet_name:
        errors.append("No outlet_name provided for this row")
        return None, "UNRESOLVED", errors, warnings
    warnings.append(f"Outlet '{outlet_name}' matched by name+territory, not a stable outlet code - verify this is correct")
    key = (_normalize(outlet_name), territory_name or "")
    candidates = ctx.customers_by_name_territory.get((_normalize(outlet_name), _normalize(territory_name) if territory_name else ""), [])
    if len(candidates) == 1:
        return str(candidates[0]), "MATCH", errors, warnings
    if len(candidates) > 1:
        errors.append(f"Ambiguous outlet '{outlet_name}' in territory '{territory_name}' matches {len(candidates)} existing outlets")
        return None, "UNRESOLVED", errors, warnings
    lat, _ = _coerce_amount(lat_raw)
    lng, _ = _coerce_amount(lng_raw)
    if lat is None or lng is None:
        warnings.append(f"Outlet '{outlet_name}' has no coordinates - cannot create it without a real location")
        return None, "UNRESOLVED", errors, warnings
    if not contact:
        warnings.append(f"Outlet '{outlet_name}' has no contact number - cannot create it")
        return None, "UNRESOLVED", errors, warnings
    norm_code = f"AUTO-{_normalize(outlet_name).replace(' ', '-')[:30]}-{uuid.uuid4().hex[:6]}"
    if norm_code not in ctx.pending_customers:
        ctx.pending_customers[norm_code] = {
            "outlet_code": norm_code, "name": outlet_name, "latitude": float(lat), "longitude": float(lng),
            "contact_number": contact, "territory_key": territory_key,
            "address": _text(mapped.get("outlet_address")) or outlet_name,
        }
    return f"NEW:{norm_code}", "CREATE", errors, warnings


# ---------------------------------------------------------------------------
# Main validate pass
# ---------------------------------------------------------------------------

async def create_import_batch(
    file_bytes: bytes,
    filename: str,
    sheet_name: str,
    column_mapping: dict[str, str],
    outlet_match_strategy: str,
    allow_generated_invoice_numbers: bool,
    current_user: User,
    session: AsyncSession,
) -> ImportBatch:
    _validate_upload(file_bytes, filename)
    columns, data_rows = _parse_full_sheet(file_bytes, sheet_name)

    # column_mapping: {excel_column: target_field_key}. Build the reverse
    # index (target_field -> excel column index) once.
    col_index = {c: i for i, c in enumerate(columns)}
    target_to_index: dict[str, int] = {}
    for excel_col, target_key in column_mapping.items():
        if not target_key:
            continue
        if excel_col not in col_index:
            raise BaseAPIException(status_code=400, detail=f"Mapped column '{excel_col}' not found in the sheet", error_code="IMPORT_BAD_MAPPING")
        if target_key not in TARGET_FIELDS:
            raise BaseAPIException(status_code=400, detail=f"Unknown target field '{target_key}'", error_code="IMPORT_BAD_MAPPING")
        target_to_index[target_key] = col_index[excel_col]

    ctx = await _build_context(session)

    parsed_rows: list[dict] = []
    error_report: list[dict] = []
    # Row-level warnings (unresolved-by-name matches, generated invoice
    # numbers, skipped-fabrication notices, etc.) - never blocking, but the
    # admin preview screen must be able to show them per row, not just as
    # aggregate counts, per the "never silently map/resolve" requirement.
    warning_report: list[dict] = []
    summary = {
        "territories_created": 0, "employees_matched": 0, "employees_unresolved": 0,
        "customers_created": 0, "customers_updated": 0,
        "invoices_created": 0, "invoices_updated": 0, "invoices_skipped_duplicate": 0,
        "payments_created": 0,
    }
    rows_processed = 0
    rows_error = 0
    rows_skipped = 0
    # Tracks (customer_key, normalized_invoice_number) -> the first row that
    # planned it, purely within THIS file. Without this, two rows for the
    # same new outlet's same invoice number would both plan CREATE and the
    # second would violate the DB's uq_invoice_customer_number constraint at
    # commit time instead of being caught here, in preview, where it belongs.
    planned_invoice_keys: dict[tuple[str, str], int] = {}
    # (outlet_code_normalized) -> set of distinct outlet_name values seen in
    # this file, surfaced as a data-quality warning (client's own stated
    # concern: master data inconsistency, not a resolution error).
    outlet_code_name_variants: dict[str, set[str]] = {}

    for i, raw_row in enumerate(data_rows):
        row_number = i + 2  # +1 header, +1 to make it 1-indexed for the user
        rows_processed += 1

        def get(field_key: str) -> Any:
            idx = target_to_index.get(field_key)
            return raw_row[idx] if idx is not None and idx < len(raw_row) else None

        mapped = {k: get(k) for k in TARGET_FIELDS}
        # Errors are tracked per plan, not as one undifferentiated row-level
        # bag. A row can carry an outlet, an invoice, AND a payment at once,
        # and they must fail independently: a payment that can't be created
        # because its employee is unresolved must never also drop an
        # otherwise-valid invoice (or the outlet itself) on the same row -
        # the same "don't let one broken field sink the rest of the row"
        # principle already applied to employee resolution. `row_errors`
        # below is only their union, kept for error_report/rows_error
        # reporting; commit gates each plan on its own list.
        customer_errors: list[str] = []
        invoice_errors: list[str] = []
        payment_errors: list[str] = []
        row_warnings: list[str] = []

        territory_key, territory_name, w = _resolve_territory(mapped, ctx)
        row_warnings += w

        employee_key, e_errors, e_warnings = _resolve_employee(mapped, ctx)
        row_warnings += e_warnings
        if employee_key:
            summary["employees_matched"] += 1
        elif _text(mapped.get("employee_code")) or _text(mapped.get("employee_name")):
            summary["employees_unresolved"] += 1

        has_outlet_data = any(_text(mapped.get(k)) for k in ("outlet_code", "outlet_name"))
        customer_key = None
        if has_outlet_data:
            customer_key, action, c_errors, c_warnings = _resolve_outlet(mapped, ctx, outlet_match_strategy, territory_key, territory_name)
            customer_errors += c_errors
            row_warnings += c_warnings

            raw_code = _text(mapped.get("outlet_code"))
            raw_name = _text(mapped.get("outlet_name"))
            if raw_code and raw_name:
                outlet_code_name_variants.setdefault(_normalize(raw_code), set()).add(raw_name)

        invoice_plan = None
        has_invoice_data = _text(mapped.get("invoice_amount")) is not None or mapped.get("invoice_amount") is not None
        if has_invoice_data:
            if customer_key is None:
                invoice_errors.append("Cannot import invoice: outlet could not be resolved")
            else:
                amount, amount_err = _coerce_amount(mapped.get("invoice_amount"))
                inv_date, date_err = _coerce_date(mapped.get("invoice_date"))
                if amount_err:
                    invoice_errors.append(f"invoice_amount: {amount_err}")
                if date_err:
                    invoice_errors.append(f"invoice_date: {date_err}")
                if amount is None:
                    invoice_errors.append("invoice_amount is required for an invoice row")
                if inv_date is None and not date_err:
                    invoice_errors.append("invoice_date is required for an invoice row")
                invoice_number = _text(mapped.get("invoice_number"))
                if not invoice_number:
                    # Stable across re-imports: built from the raw source
                    # outlet identity (unaffected by whether the outlet
                    # already exists in this run), never from customer_key,
                    # which is "NEW:<code>" on a first import but a real
                    # database id on a later one - using customer_key here
                    # would generate a *different* number every re-import
                    # once the outlet exists, defeating idempotency.
                    stable_outlet_ref = _text(mapped.get("outlet_code")) or _text(mapped.get("outlet_name"))
                    if allow_generated_invoice_numbers and stable_outlet_ref and amount is not None and inv_date is not None:
                        invoice_number = f"IMPORTED-{_normalize(stable_outlet_ref).replace(' ', '-')}-{inv_date.isoformat()}-{amount}"
                        row_warnings.append(f"No invoice_number in source - generated deterministic id '{invoice_number}'")
                    else:
                        invoice_errors.append("invoice_number is required (or enable generated invoice numbers for this batch)")
                if amount is not None and inv_date is not None and invoice_number:
                    due_date, due_err = _coerce_date(mapped.get("invoice_due_date"))
                    if due_err:
                        row_warnings.append(f"invoice_due_date: {due_err} (ignored)")
                    reported_outstanding, ro_err = _coerce_amount(mapped.get("invoice_outstanding_reported"))
                    if ro_err:
                        row_warnings.append(f"invoice_outstanding_reported: {ro_err} (ignored)")
                    dedup_key = (customer_key, _normalize(invoice_number))
                    duplicate_row = planned_invoice_keys.get(dedup_key)
                    if duplicate_row is not None:
                        row_warnings.append(
                            f"Duplicate invoice number '{invoice_number}' for this outlet also appears on row {duplicate_row} "
                            "in this file - only the first occurrence will be imported."
                        )
                        summary["invoices_skipped_duplicate"] += 1
                    else:
                        planned_invoice_keys[dedup_key] = row_number
                        existing_invoice_id = ctx.invoices_by_customer_number.get(dedup_key) if not customer_key.startswith("NEW:") else None
                        invoice_plan = {
                            "customer_key": customer_key,
                            "invoice_number": invoice_number,
                            "invoice_date": inv_date.isoformat(),
                            "due_date": due_date.isoformat() if due_date else None,
                            "amount": str(amount),
                            "brand": _text(mapped.get("invoice_brand")),
                            "imported_outstanding_amount": str(reported_outstanding) if reported_outstanding is not None else None,
                            "action": "UPDATE" if existing_invoice_id else "CREATE",
                            "existing_id": str(existing_invoice_id) if existing_invoice_id else None,
                        }
                        if existing_invoice_id:
                            summary["invoices_updated"] += 1
                        else:
                            summary["invoices_created"] += 1

        payment_plan = None
        payment_amount, pa_err = _coerce_amount(mapped.get("payment_amount"))
        if payment_amount is not None:
            if customer_key is None:
                payment_errors.append("Cannot import payment: outlet could not be resolved")
            elif employee_key is None:
                payment_errors.append("Cannot import payment: employee could not be resolved")
            else:
                pay_date, pd_err = _coerce_date(mapped.get("payment_date"))
                if pd_err:
                    payment_errors.append(f"payment_date: {pd_err}")
                if pay_date is None:
                    payment_errors.append("payment_date is required for a payment row")
                else:
                    method_raw = (_text(mapped.get("payment_method")) or "CASH").upper()
                    method = method_raw if method_raw in (m.value for m in PaymentMethod) else "CASH"
                    if method != method_raw:
                        row_warnings.append(f"Unrecognized payment_method '{method_raw}' - defaulted to CASH")
                    reference = _text(mapped.get("payment_reference"))
                    source_ref = reference or f"row-{row_number}"
                    dedup_key = (customer_key, source_ref)
                    existing_payment_id = ctx.payments_by_customer_reference.get(dedup_key) if not customer_key.startswith("NEW:") else None
                    payment_plan = {
                        "customer_key": customer_key,
                        "employee_key": employee_key,
                        "amount": str(payment_amount),
                        "payment_date": pay_date.isoformat(),
                        "payment_method": method,
                        "reference": reference,
                        "source_reference": source_ref,
                        "action": "SKIP_EXISTING" if existing_payment_id else "CREATE",
                        "existing_id": str(existing_payment_id) if existing_payment_id else None,
                    }
                    if not existing_payment_id:
                        summary["payments_created"] += 1
        elif pa_err:
            row_warnings.append(f"payment_amount: {pa_err} (payment row ignored)")

        row_errors = customer_errors + invoice_errors + payment_errors
        if row_errors:
            rows_error += 1
            for err in row_errors:
                error_report.append({"row": row_number, "error": err, "suggested_fix": "Correct the source data or the column mapping, then re-upload."})
        elif customer_key is None and invoice_plan is None and payment_plan is None:
            rows_skipped += 1

        for warn in row_warnings:
            warning_report.append({"row": row_number, "warning": warn})

        parsed_rows.append({
            "row_number": row_number,
            "territory_key": territory_key,
            "territory_name": territory_name,
            "employee_key": employee_key,
            "customer_key": customer_key,
            "customer_errors": customer_errors,
            "invoice_errors": invoice_errors,
            "payment_errors": payment_errors,
            "invoice_plan": invoice_plan,
            "payment_plan": payment_plan,
            "errors": row_errors,
            "warnings": row_warnings,
        })

    # A "NEW:<key>" territory/customer plan staged by _resolve_territory /
    # _resolve_outlet is only confirmed for creation if at least one row that
    # references it resolved it cleanly. Gated on customer_errors (not the
    # row's full error union): a row whose outlet resolved fine but whose
    # *payment* or *invoice* separately failed must still get its outlet
    # created - the same "don't let one broken field sink the rest of the
    # row" rule already applied to invoice/payment creation below.
    # _resolve_territory never itself errors, so any row that names a
    # territory confirms it regardless of what else went wrong on that row.
    confirmed_territory_keys = {
        r["territory_key"] for r in parsed_rows
        if r["territory_key"] and r["territory_key"].startswith("NEW:")
    }
    confirmed_customer_keys = {
        r["customer_key"] for r in parsed_rows
        if r["customer_key"] and r["customer_key"].startswith("NEW:") and not r["customer_errors"]
    }
    ctx.pending_territories = {
        norm: name for norm, name in ctx.pending_territories.items()
        if f"NEW:{norm}" in confirmed_territory_keys
    }
    ctx.pending_customers = {
        norm: payload for norm, payload in ctx.pending_customers.items()
        if f"NEW:{norm}" in confirmed_customer_keys
    }

    summary["territories_created"] = len(ctx.pending_territories)
    summary["customers_created"] = len(ctx.pending_customers)
    # customers_updated: distinct existing customer ids referenced as MATCH
    matched_customer_ids = {
        r["customer_key"] for r in parsed_rows
        if r["customer_key"] and not r["customer_key"].startswith("NEW:")
    }
    summary["customers_updated"] = len(matched_customer_ids)
    # The actual payload needed to create each pending customer at commit
    # time (name/coordinates/contact/territory) - keyed by "NEW:<code>" to
    # match parsed_rows' customer_key, so commit doesn't need to re-derive
    # anything from the source file.
    summary["customer_plans"] = {
        f"NEW:{code}": payload for code, payload in ctx.pending_customers.items()
    }
    # Data-quality signal (client's own stated concern): the same outlet
    # code used with inconsistent outlet names across the file.
    inconsistent_codes = {code: names for code, names in outlet_code_name_variants.items() if len(names) > 1}
    summary["duplicate_outlet_codes_with_inconsistent_names"] = [
        {"outlet_code": code, "names_seen": sorted(names)} for code, names in inconsistent_codes.items()
    ]
    summary["warnings"] = warning_report
    summary["rows_with_warnings"] = len({w["row"] for w in warning_report})

    batch = ImportBatch(
        filename=filename,
        sheet_name=sheet_name,
        uploaded_by=current_user.id,
        column_mapping=column_mapping,
        outlet_match_strategy=outlet_match_strategy,
        status=ImportStatus.VALIDATED,
        parsed_rows=parsed_rows,
        error_report=error_report,
        summary=summary,
        rows_processed=rows_processed,
        rows_created=summary["customers_created"] + summary["invoices_created"] + summary["payments_created"] + summary["territories_created"],
        rows_updated=summary["customers_updated"] + summary["invoices_updated"],
        rows_skipped=rows_skipped,
        rows_error=rows_error,
    )
    session.add(batch)
    await session.commit()
    await session.refresh(batch)
    return batch


# ---------------------------------------------------------------------------
# Commit
# ---------------------------------------------------------------------------

async def commit_import_batch(batch_id: uuid.UUID, current_user: User, session: AsyncSession) -> ImportBatch:
    result = await session.execute(select(ImportBatch).where(ImportBatch.id == batch_id))
    batch = result.scalar_one_or_none()
    if batch is None:
        raise BaseAPIException(status_code=404, detail="Import batch not found", error_code="IMPORT_BATCH_NOT_FOUND")
    if batch.status != ImportStatus.VALIDATED:
        raise BaseAPIException(status_code=409, detail=f"Batch is {batch.status.value}, cannot commit", error_code="IMPORT_BATCH_NOT_VALIDATED")

    territory_ids: dict[str, uuid.UUID] = {}
    customer_ids: dict[str, uuid.UUID] = {}
    counters = {"created": 0, "updated": 0, "skipped": 0, "error": 0}

    try:
        # Pass 1: create pending territories. Never itself a source of
        # errors (see _resolve_territory), so any row naming one confirms
        # it regardless of what else failed on that row.
        pending_territory_names = {
            r["territory_key"]: r["territory_name"]
            for r in batch.parsed_rows
            if r["territory_key"] and r["territory_key"].startswith("NEW:")
        }
        for key, name in pending_territory_names.items():
            territory = Territory(name=name)
            session.add(territory)
            await session.flush()
            territory_ids[key] = territory.id

        def resolve_territory_id(territory_key: Optional[str]) -> Optional[uuid.UUID]:
            if not territory_key:
                return None
            if territory_key.startswith("NEW:"):
                return territory_ids.get(territory_key)
            return uuid.UUID(territory_key)

        # Pass 2: create pending customers (need resolved territory ids).
        # The payloads (name/coordinates/contact) were computed once during
        # validate and stored in summary.customer_plans precisely so commit
        # doesn't need the source file again.
        for ck, payload in (batch.summary.get("customer_plans") or {}).items():
            customer = Customer(
                name=payload["name"],
                contact_number=payload["contact_number"],
                address=payload.get("address") or payload["name"],
                location=f"POINT({payload['longitude']} {payload['latitude']})",
                outlet_code=payload["outlet_code"],
                territory_id=resolve_territory_id(payload.get("territory_key")),
                created_by=current_user.id,
            )
            session.add(customer)
            await session.flush()
            customer_ids[ck] = customer.id
            counters["created"] += 1

        def resolve_customer_id(customer_key: Optional[str]) -> Optional[uuid.UUID]:
            if not customer_key:
                return None
            if customer_key.startswith("NEW:"):
                return customer_ids.get(customer_key)
            return uuid.UUID(customer_key)

        # Pass 3: invoices. Gated on invoice_errors specifically - a payment
        # failure elsewhere on this row must not drop an otherwise-valid
        # invoice.
        for r in batch.parsed_rows:
            if r["invoice_errors"] or not r["invoice_plan"]:
                continue
            plan = r["invoice_plan"]
            cid = resolve_customer_id(plan["customer_key"])
            if cid is None:
                counters["error"] += 1
                continue
            if plan["action"] == "UPDATE" and plan["existing_id"]:
                inv_result = await session.execute(select(Invoice).where(Invoice.id == uuid.UUID(plan["existing_id"])))
                invoice = inv_result.scalar_one()
                invoice.invoice_date = date.fromisoformat(plan["invoice_date"])
                invoice.due_date = date.fromisoformat(plan["due_date"]) if plan["due_date"] else None
                invoice.amount = Decimal(plan["amount"])
                invoice.brand = plan["brand"]
                invoice.imported_outstanding_amount = Decimal(plan["imported_outstanding_amount"]) if plan["imported_outstanding_amount"] else None
                session.add(invoice)
                counters["updated"] += 1
            else:
                invoice = Invoice(
                    customer_id=cid,
                    invoice_number=plan["invoice_number"],
                    invoice_date=date.fromisoformat(plan["invoice_date"]),
                    due_date=date.fromisoformat(plan["due_date"]) if plan["due_date"] else None,
                    amount=Decimal(plan["amount"]),
                    brand=plan["brand"],
                    source=InvoiceSource.EXCEL_IMPORT,
                    source_reference=f"{batch.filename}:row{r['row_number']}",
                    imported_outstanding_amount=Decimal(plan["imported_outstanding_amount"]) if plan["imported_outstanding_amount"] else None,
                    created_by=current_user.id,
                )
                session.add(invoice)
                counters["created"] += 1

        # Pass 4: payments. Gated on payment_errors specifically - an
        # invoice failure elsewhere on this row must not drop an
        # otherwise-valid payment.
        for r in batch.parsed_rows:
            if r["payment_errors"] or not r["payment_plan"]:
                continue
            plan = r["payment_plan"]
            if plan["action"] == "SKIP_EXISTING":
                counters["skipped"] += 1
                continue
            cid = resolve_customer_id(plan["customer_key"])
            eid = uuid.UUID(plan["employee_key"]) if plan["employee_key"] else None
            if cid is None or eid is None:
                counters["error"] += 1
                continue
            payment = Payment(
                customer_id=cid,
                employee_id=eid,
                visit_id=None,
                amount=Decimal(plan["amount"]),
                payment_method=PaymentMethod(plan["payment_method"]),
                payment_date=date.fromisoformat(plan["payment_date"]),
                utr_reference=plan["reference"],
                status=PaymentStatus.VERIFIED,
                source=PaymentSource.EXCEL_IMPORT,
                source_reference=plan["source_reference"],
                created_by=current_user.id,
            )
            session.add(payment)
            counters["created"] += 1

        batch.status = ImportStatus.COMMITTED
        batch.committed_at = datetime.now(tz=timezone.utc)
        batch.committed_by = current_user.id
        session.add(batch)
        await session.commit()
        await session.refresh(batch)
        return batch
    except Exception as exc:
        await session.rollback()
        batch.status = ImportStatus.FAILED
        batch.failure_reason = str(exc)[:2000]
        session.add(batch)
        await session.commit()
        await session.refresh(batch)
        raise BaseAPIException(status_code=500, detail=f"Import failed and was rolled back: {exc}", error_code="IMPORT_COMMIT_FAILED")


async def list_import_batches(session: AsyncSession, skip: int = 0, limit: int = 50) -> list[ImportBatch]:
    result = await session.execute(
        select(ImportBatch).order_by(ImportBatch.uploaded_at.desc()).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


async def get_import_batch(batch_id: uuid.UUID, session: AsyncSession) -> ImportBatch:
    result = await session.execute(select(ImportBatch).where(ImportBatch.id == batch_id))
    batch = result.scalar_one_or_none()
    if batch is None:
        raise BaseAPIException(status_code=404, detail="Import batch not found", error_code="IMPORT_BATCH_NOT_FOUND")
    return batch
