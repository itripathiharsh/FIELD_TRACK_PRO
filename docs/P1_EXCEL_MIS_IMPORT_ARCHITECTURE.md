# P1 Architecture Design — Excel/MIS Import

Status: **architecture design + a working, column-agnostic preview step**.
The client's actual source file has not arrived, so this document
deliberately does not invent its columns. What's implemented now is the one
piece of the pipeline that doesn't require knowing them.

## Why this exists

Section 7/23/24 of the P1 spec: the data architecture must support
importing external financial data via Excel/MIS, described as an
Inspect → Map → Validate → Detect duplicates → Show migration errors →
Import → Verify totals pipeline. Building the "Map" step against guessed
column names would very likely be wrong and would need rework anyway once
the real file arrives — so only "Inspect" is implemented as working code
today; the rest of this document specifies the design the remaining steps
will follow.

## What's implemented now

`POST /api/v1/imports/preview` (admin-only; `app/api/v1/imports.py`,
`app/services/import_service.py`). Accepts an uploaded `.xlsx` file and
returns:

```json
{
  "sheet_name": "Sheet1",
  "columns": ["Retailer Name", "Emp Code", "Territory", "Invoice No", "Invoice Date", "Amount", "Brand"],
  "sample_rows": [["Balaji Enterprises", "EMP-001", "Lucknow", "INV-9001", "2026-06-01", "45000", "Usha"]],
  "total_data_rows": 2,
  "truncated": false
}
```

This makes no assumption about what any column means — it reports exactly
what's in the file. Row values are all returned as strings; type coercion
(dates, numbers) belongs to the mapping step, once real field meanings are
confirmed, not to a generic preview.

Tested: `tests/test_import_preview.py` (empty file, oversized file,
non-.xlsx extension, unreadable/corrupt file, blank header cells,
truncation past the 20-row preview cap) plus a live end-to-end run against
the actual endpoint (admin succeeds, employee 403s, unauthenticated 401s).

## Designed but not built: the remaining pipeline

### 1. Column mapping (admin-configured, not hardcoded)

Once a real file is available, the admin should see the detected columns
(from `/imports/preview`) and assign each one to a FieldTrack target field
from a fixed list:

```
Employee/FOS -> employees.employee_code (existing field)
Territory    -> territories.name (existing field)
Outlet ID    -> customers.outlet_code (added this pass, for exactly this)
Outlet Name  -> customers.name (fallback identity only - see below)
Invoice No   -> invoices.invoice_number
Invoice Date -> invoices.invoice_date (authoritative aging source)
Due Date     -> invoices.due_date (optional, display-only)
Amount       -> invoices.amount
Brand        -> invoices.brand (optional)
(unmapped)   -> ignored, or held as an "unknown" bucket - see below
```

This mapping is a **per-import configuration**, not new code per file
layout, so the client's actual (still-unknown) column names never need to
be hardcoded anywhere.

### 2. Identity resolution (the hard part)

Per the client's own stated concern (similarly-named retailers), a row's
outlet must resolve to an existing `customers.id` via `outlet_code`, **not**
by fuzzy-matching `customers.name`. If a row's outlet code doesn't match any
existing customer:
- **Do not** silently create a new customer or guess a match by name
  similarity.
- Surface it as a named migration error ("row 14: outlet_code 'OUT-042' not
  found") for an admin to resolve (either the code is wrong in the source
  file, or the outlet genuinely doesn't exist in FieldTrack yet and needs
  to be created first, deliberately, by an admin).

### 3. Validation rules (applied per row, before any commit)

- Amount parses as a positive number.
- Invoice date parses as a real date, not in the future.
- `(customer_id, invoice_number)` doesn't already exist (the same
  uniqueness constraint `Invoice` already enforces at the DB level for
  manual entry - see `uq_invoice_customer_number`) - a repeat becomes a
  reported duplicate, not a duplicate row in the table.
- Any field explicitly mapped to a target that expects a type the raw value
  can't be coerced to (e.g. "Amount" column containing "N/A") is a reported
  per-row error, not a crash of the whole import.

### 4. Dry-run before commit

The importer should run entirely against the parsed file first, producing a
report of {rows that would import cleanly, rows with validation errors,
rows that are duplicates}, and only write to the database once an admin
explicitly confirms after reviewing that report. This mirrors exactly the
client's own described sequence: "Validate → Detect duplicates → Show
migration errors → Import."

### 5. Provenance and verification

Every row that does commit becomes an `Invoice` with `source =
EXCEL_IMPORT` and `source_reference` set to something that identifies the
originating row (e.g. `"{filename}:row{n}"` or the source file's own invoice
ID if present) - already supported by the schema added this pass, no
further schema change needed. After a batch commits, "verify totals" means
comparing the sum of successfully-imported amounts against a total the admin
can cross-check from the source file/report, surfaced back in the import UI.

## Unresolved — needs client input before building the mapping step

- What do the client's spreadsheet columns actually named "days" and
  "counts" represent? (Visit frequency? Working days? Outlet visit counts
  to date? Something else?) Not guessed anywhere in this codebase.
- Is "price"/"remaining quantity" an inventory/stock concept requiring a
  new module, or informal notes that belong in a text field? No inventory
  model exists in FieldTrack and none should be built speculatively.
- Exact historical period to import (the client mentioned "3-6 months,"
  "possibly April 2026 onward," "potentially older" - not yet confirmed).
- Whether the client's outlet identity in their own systems is literally
  called "Outlet ID," a Tally ledger name/alias, or something else -
  determines what `outlet_code` should actually be populated with during
  a first historical load.

None of these are answerable from the codebase or from general Tally/Excel
knowledge - they require the client's actual file and a direct question.
