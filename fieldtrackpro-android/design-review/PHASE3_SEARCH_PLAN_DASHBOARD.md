# Monthly Plan, customer search, Off-Beat Visit and Employee Dashboard

Android-only changes on `feature/android-premium-ui`. No backend, database, Tally, Tally Agent or Distribution-scope
change. Investigation of data used the **local dev database** (`fieldtrackpro_dev` on this PC, the backend the debug
APK talks to) in read-only transactions; production was not queried.

## 1. Monthly Plan HTTP 401 – root cause

`MonthlyPlanningViewModel` is created by `MainActivity` (`by viewModels`) when the navigation graph is first composed,
which is on the **splash/login screen, before sign-in**. Its `init {}` immediately called
`GET /api/v1/visit-planning/my-plan`, `GET …/analytics/my-month` and `GET /api/v1/customers`.

- Those requests carried **no `Authorization` header** (no token yet), so the backend answered **401**.
- `TokenAuthenticator` deliberately does not refresh a request that never carried a session, so the 401 reached the screen.
- The view-model stored "Failed to load monthly plan (401)", and the screen **never reloaded when opened**. So after
  signing in, the user still saw the 401 with zero counts.
- The customer list failed the same way, and errors were shown as "No matching customers found".

The endpoint, HTTP method, token attachment, refresh logic and backend RBAC are correct. `my-plan` is `AnyAuth`
(EMPLOYEE allowed), and requests made after sign-in carry the token.

**Fix:** no network call in `init`. The plan loads when a signed-in user opens the screen (`onScreenOpened`). It
reloads for a different user and is reset on logout. Load errors are classified (session ended / no access / offline /
server), each with a recovery action. **No metrics are shown unless the plan for that month actually loaded**, and the
previous month's numbers are never shown after a failed month change. Action errors (add/edit) are separate from load
errors. Duplicate submissions are ignored.

## 2. Customer search – root causes

Backend (`customer_repo.list_accessible_by_employee`, read-only inspection):
- Every token is ANDed with `ILIKE '%token%'` across name, code, address, contact fields and linked Tally ledger
  names. Results are ordered **alphabetically by name**, with **no relevance**, and capped at **50** for employee
  searches.
- Queries under 3 characters only search the employee's scope; 3+ characters also search the whole directory
  (returned redacted, for the off-beat picker).
- Hidden: merged outlets and non-debtor Tally ledgers.

Effects:
- For `s` there are 4,893 matching outlets in the dev DB. The first 50 alphabetically are mostly names starting with
  "A" whose **address** contains an "s", so names starting with S never appear.
- Exact or prefix matches can be pushed out of the 50-row page.

Android:
- No debounce; one request per keystroke.
- Errors (401, offline) were rendered as "No matching customers found".
- The Monthly Plan picker started from a 50-row first page.
- Monthly Plan and Off-Beat used different code paths.

**Fix (Android, no API change), one shared implementation (`search/CustomerSearch.kt`) for both pickers:**
- The employee's **complete authorized outlet list** is loaded once per session: `GET /customers` without `search`,
  paged until complete, cached 10 minutes, cleared on logout. It is searched locally, so pagination cannot hide a
  match inside the employee's own outlets.
- For queries of 3+ characters, a **debounced (300 ms)** directory search is merged in. A generation counter
  guarantees a **slow, older response never overwrites a newer query**.
- **Relevance ranking**, case-insensitive and whitespace-normalised:
  1. exact name
  2. name starts with
  3. name contains (words in any order)
  4. exact code
  5. code partial
  6. address / area / territory
  7. other server-side match (e.g. Tally ledger name)

  Ties: word-prefix first, then name A–Z, then code.
- Short queries (1–2 characters) search only the employee's outlets, with a hint to type 3+ letters. The
  directory search shows "Showing the best matches of N" when the server has more than it returned. Errors are
  shown as errors with Retry, never as "no results". Outlets outside the employee's scope are flagged "Other area";
  their data remains redacted by the server.

Access control is unchanged: the server decides what each employee can see; Android only ranks what it receives.

## 3. "ABC Electronics" – investigation result (local dev database)

- **338** customers named exactly "ABC Electronics", codes `OUT-xxxx`, addresses "Chandni Chowk, Delhi" or
  "123 Market Road, City", created 11 Oct to 19 Nov 2026.
- **All 338 were created by `@fieldtrack.test` accounts**: they are automated test fixtures (AGENTS.md: test data must
  not be in production). None has a Tally debtor ledger. 186 are attached to some territory/area/assignment (test
  reps), 152 to none.
- The test employee used in the screenshots (Neeraj Rajput, code 11015) has **no territory, area or outlet
  assignment** in the dev DB. His scope is therefore effectively empty, so short queries return nothing; "ABC" and
  longer use the directory search.
- Why it did not appear: the Monthly Plan view-model's requests were failing with 401 (section 1), and the failure
  was shown as "No matching customers found". With the fix, searching `ABC Electronics`, `abc electronics` or `ABC`
  returns these rows (exact matches first; out-of-scope rows flagged "Other area", redacted by the server).
- **Production was not queried.** Per AGENTS.md these fixtures should not exist there; if a real "ABC Electronics"
  exists in production, the same search path applies. A read-only production check needs your approval.

## 4. Employee Dashboard – data sources (existing APIs only)

| Metric | Source | Attribution / definition |
|---|---|---|
| Verified today / this month | `GET /workday/today?work_date=<each day>` → `summary.collections_verified_amount` | Server sums payments with `employee_id = me` and status VERIFIED, by payment creation day. Tally receipts (no employee) are never included. |
| Recorded this month / not yet verified | same → `collections_total_amount` (minus verified) | Includes pending and rejected; the API does not split them, so the label says "not yet verified". |
| Daily trend | same, per day | Verified amount per day. Days that failed to load are counted and flagged ("totals may be lower"). |
| Planned / completed / completion / missed | `GET /visit-planning/analytics/my-month` | Visits attributed by `visit.employee_id`. |
| Workdays / visits done | daily workday summaries | A day counts as worked when a work session was started or completed. |
| Total outstanding (portfolio) | `GET /customers/{id}/account` → `total_outstanding` per outlet in the current portfolio | Customer-level, current portfolio, **not** money collected by the employee, **not** historical ownership. |
| Overdue per outlet | account → `overdue_amount` | Server figure. |
| Ageing buckets / past due | `GET /customers/{id}/invoices` → `remaining_amount` by `due_date` | Days past due = today − due date; buckets: not yet due, 1–30, 31–60, 61–90, >90, no due date. Fetched only for outlets with a balance. |
| Last visit / last payment | account → `most_recent_visit_date`, `most_recent_payment` | Customer facts; the last payment may be a Tally receipt or another employee's collection, and is labelled so. |
| My outlets | the authorized outlet list (same as search) | Server scope: assigned, covered area / home territory, or on the employee's planned visits. |

Collections and outstanding are never added together. Outlets whose account cannot be loaded are excluded from
totals and counted on screen. **Not available** (shown as such): collection history by outlet and an all-time
total, because no existing API lists an employee's own payments.

Access: the dashboard opens only for an explicit EMPLOYEE role and uses employee-scoped endpoints; ADMIN,
SUPER_ADMIN and ACCOUNTANT accounts get an explanation to use the web reports (no RBAC change).

## 5. Backend / database changes – proposals only (need your approval, not implemented)

1. **Relevance ordering in customer search** (`customer_repo.list_accessible_by_employee` and `list_by_territory`):
   `ORDER BY` a CASE rank (exact name, name prefix, name contains, exact code, code prefix, address), then name;
   optionally `pg_trgm` GIN indexes on `customers.name` and `outlet_code`. Why: the 50-row cap currently cuts off the
   best directory matches. Contract unchanged (same parameters and fields, better order).
2. **`GET /api/v1/performance/me/collections?from&to`** (EMPLOYEE, own data only): the employee's own payments
   (`employee_id = me`) with outlet, amount, status, date, plus linked-receipt flag. Why: collection history,
   outlet-wise breakdown and all-time totals (currently "not available"). New endpoint only.
3. **`GET /api/v1/performance/me/portfolio`** (EMPLOYEE): one call returning outstanding, overdue, due-date ageing,
   last visit and last payment per outlet in scope, plus an `assigned` flag. Why: replaces N account + N invoice calls
   and distinguishes directly assigned outlets from area/territory scope. New endpoint only.
4. **Assignment history** (`valid_from` / `valid_to` on customer and area assignments; stop hard-deleting area
   assignments). Why: historical portfolio ownership. Schema change, needs a migration.
5. **Clean-up of `@fieldtrack.test` fixtures** (e.g. the 338 "ABC Electronics") in any shared or production
   database, per AGENTS.md. Data change, needs explicit approval.

## 6. Verification

- Unit tests: Monthly Plan auth/error handling, search ranking, case-insensitivity, pagination, stale responses,
  debounce, employee access control, dashboard calculations and financial attribution
  (`app/src/test/.../phase3/`), plus screenshot renders 12–20 in `design-review/screens/`.
- Not tested on a real device; no device or emulator was available.
