# Employee performance dashboard: feature proposal (feasibility only)

Status: **proposal, nothing implemented.** No backend API, database migration or production query was created or run.
Source: read-only inspection of `fieldtrackpro-backend/app` (models, services, routes, RBAC) on 2026-11-22.

## Ground rules

1. **Verified field data only** is attributed to an employee: visits, workdays, monthly plans and field (`MANUAL`) collections.
2. **Unlinked Tally receipts are never attributed to an employee** (`payments.employee_id` is NULL for them). No assignment-based guessing and no FOS-name or fuzzy matching.
3. Customer-level financial data (Tally invoices, receipts, outstanding) is shown **as customer data**, in a separate panel, labelled as such.
4. Existing API contracts, RBAC, Distribution-only scope rules and the Tally integration stay unchanged.

## What the data supports today

| Figure | Source | Attribution | Since |
|---|---|---|---|
| Visits planned / completed / missed / ad-hoc | `visits` (`employee_id`, `scheduled_at`, `status`, `visit_type`) | Verified | first app use (real data loaded 2026-08-22) |
| Check-in / check-out times and GPS | `visits.check_in_at`, `check_out_at`, locations | Verified | same |
| Days worked, start/end time, hours | `employee_work_sessions` | Verified | table added 2026-08-30 |
| Plan vs actual (adherence) | `monthly_visit_plans`, `planned_visits` + `visits` | Verified | table added 2026-09-02 |
| Field collections (amount, method, status) | `payments` where `source = MANUAL`; `employee_id` copied from the visit (`payment_service.py:252`) | Verified | first app use |
| A Tally receipt linked to a field collection | `payments.tally_receipt_payment_id` (release 3.0 relink) | Verified by link: it is the same money as the field collection, so count it once as the field collection | since relinking |
| All other Tally receipts | `payments` (Tally source, `employee_id` NULL) | **Not attributable**: customer-level only | ~1.5 years |
| Customer invoices / outstanding / ageing | `invoices`, Tally ledgers, `outlet_financial_snapshots` | Customer-level only | ~1.5 years (Tally), BI snapshot dates |

Row counts in production were **not** queried. A SELECT-only count (per table: count, min/max date, payments by `source` and whether `employee_id` is set) is the first step once you approve it.

## Proposed screens

### Employee app: "My performance" (new, read-only)
- Period switch: this month, last month, pick a month (limited to months with data).
- Tiles: visits done of planned, plan adherence %, days worked and average hours, field collections (verified / not yet verified / rejected).
- Month-by-month trend (visits done, field collections).
- "My customers": per customer, visit count, last visit date, field collections by this employee. Tapping a customer opens their **visit history** (dates, status, check-in time).
- Footnote: "Shows your own field activity only. Tally receipts that are not linked to your field collections are not included."

### Web admin / accountant: "Field performance" (new, read-only)
- Employee table: visits done/planned, adherence %, days worked, field collections. Sortable, filter by territory/month, export.
- Drill-down per employee, with two visually separate panels:
  1. **Verified field activity** (as above, plus the trend).
  2. **Customer financials for currently assigned outlets**, labelled "Customer data: not collections by this employee". Invoices, outstanding and Tally receipts appear here as customer totals only.

## APIs and database changes needed (for approval later)

New read-only endpoints (no change to existing ones):
- `GET /api/v1/performance/me?from=YYYY-MM&to=YYYY-MM`: EMPLOYEE only; scoped on the server to the caller's own `employee_id` (no id parameter accepted).
- `GET /api/v1/performance/me/customers` and `/me/customers/{customer_id}/visits`: own customers and visit history.
- `GET /api/v1/performance/employees` and `/employees/{employee_id}` (+ `/customers`): ADMIN, SUPER_ADMIN and read-only ACCOUNTANT (same as the existing `FinanceRead` rule).
- Every figure in a response carries `attribution: "VERIFIED_FIELD"` or `"CUSTOMER_LEVEL"`.

Database (optional, improves accuracy and speed):
- Indexes on `visits (employee_id, scheduled_at)` and `payments (employee_id, payment_date)`.
- Assignment history: `valid_from` / `valid_to` on customer and area assignments, and stop hard-deleting area assignments (`employee_area_service.py:153`). Without this, "assigned outlets" is always the *current* assignment.
- Separately recommended: replace the substring FOS-name match in the BI import (`import_service.py:572-576`, where "raj" matches "neeraj") with exact/alias matching. This affects existing reports, so it needs its own approval.

## Accurate historical range
- Field metrics: from each employee's first app activity (no earlier than late Aug 2026).
- Customer financial totals: the imported Tally range (~1.5 years), customer level only.
- "Assigned outlets" history: only from when assignment history is added; before that, current assignments only.

## Known data-quality limits
- Tally receipts carry no employee (by design, they stay unattributed).
- Customer and area assignments are current-only.
- Workday rows created before app 1.3.0 may contain (0,0) end coordinates (fixed in the app: End Day can no longer send 0,0). Exclude them from any location analysis.
- Offline actions use device timestamps and the device's local date.
- Payment statuses must be split (pending / verified / rejected); the current daily summary only gives total and verified.
- Test entities named in AGENTS.md (REP-* reps, test outlets, mock visits) must be confirmed absent from production before reporting.
- Some employees have no employee code (the profile showed "N/A"); reports should key on `employee_id`.

## Permissions
- EMPLOYEE: own data only, enforced on the server.
- ADMIN / SUPER_ADMIN: all employees.
- ACCOUNTANT: read-only, all employees.
- No new role; no change to existing RBAC.
