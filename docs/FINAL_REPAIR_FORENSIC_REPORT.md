# FieldTrack Pro — Final Repair Forensic Report

**Pass:** closure audit over the completed repair programme
**Method:** inspect → reason → compare to spec → reproduce → test → only then fix
**Entry commit:** `2d6286f` · **Exit commit:** `2d29baa`
**Companion documents:** `REPAIR_BASELINE.md`, `REPAIR_LEDGER.md`,
`REPAIR_DECISIONS.md`, `REPAIR_VERIFICATION.md`, `SECRET_ROTATION.md`

---

## 1. Executive summary

This pass did **not** accept the previous programme's conclusions. Every
CRITICAL fix was re-tested by deliberately reverting it (mutation testing), the
API contract was diffed field-by-field against the live OpenAPI schema, the
migration chain was round-tripped on a scratch database, and the running system
was probed with hostile payloads and forged tokens.

**Result: the previously reported status was accurate, but incomplete. Four
further defects were found, and one previously reported fix was incomplete.**

| Finding | Severity | How found |
|---|---|---|
| **FT-072** — PostGIS geofence authority untested at the boundary | MEDIUM | Mutation testing |
| **FT-073** — `GET /employees` omitted the linked user account | MEDIUM | Contract diffing |
| **FT-074** — admin override could resurrect a terminal visit | **HIGH** | Adversarial API probing |
| **FT-070 (incomplete)** — `CheckOutScreen` still coerced coordinates to `(0,0)` | HIGH | Exhaustive pattern hunt |

All four are now fixed, each with a test that fails without the fix.

The most serious, **FT-074**, produced genuinely corrupt data: a COMPLETED
visit forced back to PENDING persisted with **both** check-in and check-out
timestamps still set — a state the domain cannot otherwise reach.

**Nothing was changed that was already correct.** Three source files and one
Kotlin file were modified; three test files were added. No visual change was
made.

---

## 2. Repository inventory

451 tracked files, working tree clean.

| Area | Files | Notes |
|---|---|---|
| `fieldtrackpro-backend/app` | 76 | FastAPI, 40 endpoints, layered router → service → repository |
| `fieldtrackpro-backend/tests` | 24 | 88 unit + 135 integration |
| `fieldtrackpro-backend/alembic` | 9 | 5 revisions, linear, single head |
| `fieldtrackpro-web/src` | 44 | React 18 + Vite + TS, 68 tests |
| `fieldtrackpro-android` | 55 | Kotlin/Compose — **not buildable here** |
| `docs` | 9 | repair programme documentation |
| `Sentio Mind application` | 212 | locked specifications and design system |

**Note on the design-system path:** the path given in the brief
(`F:\field track pro\Sentio Mind application\stitch_fieldtrack_pro_design_system`)
does not exist. The actual location is
`F:\sentio wala\field track pro\Sentio Mind application\Sentio Mind application\stitch_fieldtrack_pro_design_system`,
which is what was audited against.

---

## 3. Defect ledger reconciliation

All four repair documents exist. Rather than trust their VERIFIED claims, each
CRITICAL/HIGH fix was **mutation tested** — the fix was reverted and the suite
re-run:

| Defect | Mutation applied | Tests that failed | Detection |
|---|---|---|---|
| FT-001 | restore the fake-ADMIN fallback | 6 | ✅ |
| FT-002 | remove ownership scoping | 3 | ✅ |
| FT-004 | return `(0.0, 0.0)` from WKB decode | 1 | ⚠️ weak → strengthened |
| FT-005 | delete `list_by_visit` | 4 | ✅ |
| FT-036 | disable duplicate detection | 2 | ✅ |
| FT-041 | disable the rate-limit check | 5 | ✅ |

**FT-004's detection was weaker than claimed.** Replacing the PostGIS distance
with `None` (forcing the Haversine fallback) failed **zero** tests. That gap is
FT-072 below. Every mutation was reverted and the suite re-verified green.

Ledger totals reconcile. No incorrectly closed items, no duplicates, no test
found passing for the wrong reason other than the FT-004 gap.

---

## 4. Security audit

19 controls re-verified; additionally probed live:

| Probe | Result |
|---|---|
| Malformed JSON, `null` body, array-for-object | 422 |
| Unknown key (`extra="forbid"`) | 422 |
| Invalid UUID in path | 422 |
| Latitude 999 / longitude −999 / null / string | 422 |
| `contact_number` 21 chars, radius 0, radius −5 | 422 |
| Invalid enum, invalid datetime, 7-char password, `MANAGER` role | 422 |
| No token / empty bearer / garbage / Basic scheme | 401 |
| **`alg=none` forged admin JWT** | **401** |
| Employee → 6 admin operations | 403 |
| 4 missing resources | 404 |

**No probe produced a 500 or an unintended 2xx.** Secret scan across 451
tracked files: **0 hits**.

---

## 5. API contract audit

- **40 endpoints**; every non-public one declares authentication.
- **0 camelCase leaks** into the contract.
- Enums consistent: `VisitStatus`(5), `Role`(2), `MediaType`(2), `GeoVerificationType`(2).
- Frontend types diffed against OpenAPI: only `Visit.customer_name`,
  `employee_name`, `geo_failure_count` are declared beyond the API — all
  **optional with real fallbacks**, forward-compatible, not defects.
- **`Employee` mismatch was a real defect → FT-073.**
- Android DTOs diffed against OpenAPI: **0 fields not defined by the contract.**

---

## 6. Database audit

- Chain linear, **single head** `c3d81b6f4a52`, current == head.
- **Full `downgrade base` → `upgrade head` round trip succeeded on a scratch
  database** (never previously tested). Live database untouched.
- 0 orphans across 9 referential checks; all constraints and indexes present;
  PostGIS 3.5, SRID 4326; audit table grants = `INSERT, SELECT` only.
- **Exhaustive `(0,0)` fallback hunt** across Python, TypeScript and Kotlin
  using 12 patterns: the only live matches were in `CheckOutScreen.kt`
  (FT-070 incomplete). Now **zero**. Remaining matches are documentation
  comments describing the historical defect.

---

## 7. Business logic audit

Visit lifecycle verified end-to-end in the browser: PENDING → IN_PROGRESS →
COMPLETED, with far-away check-in correctly rejected and status unchanged.

**AMB-001 (ambiguity, no change made):** the state machine permits
`IN_PROGRESS → MISSED` and `FLAGGED → MISSED`, which `19_business_logic.md` §1
does not list. Both are currently **unreachable** — the scheduler selects only
PENDING rows. Left alone; recorded for product decision rather than changed on
a guess.

**FT-074 (fixed):** `admin_force_status` bypassed the machine entirely and
could reopen a terminal visit. Terminal states are now protected with 409 while
every legitimate override the API design grants still works.

---

## 8. Frontend behavioural audit

Static sweep of all 13 pages:

- **Every `<button>` has a handler or is `type="submit"`** — 0 dead controls.
- **All 5 `<select>` controls** have `value`, `onChange` and an `id`.
- **All 7 `<form>` elements** have `onSubmit`.
- Loading/error/empty states present on every data-driven page.

Browser-verified: all 11 admin pages render with no `undefined`, `NaN` or
`[object Object]`; **0 console errors**; cancel does not persist; search
filters; created records survive reload.

---

## 9. Android static audit

**BLOCKED — REQUIRES ANDROID BUILD ENVIRONMENT. NO BUILD CLAIM IS MADE.**

Final attempt recorded: `gradlew.bat` **absent**, `java` **absent**,
`ANDROID_HOME` **unset**.

| Item | Classification |
|---|---|
| FT-024 auth DTOs match `CurrentUserRead` | VERIFIED STATICALLY |
| FT-025 visit/customer DTOs match contract | VERIFIED STATICALLY |
| FT-026 `geofence_radius_m` | VERIFIED STATICALLY |
| FT-027 EncryptedSharedPreferences | VERIFIED STATICALLY |
| FT-070 no `(0,0)` coercion (both screens) | VERIFIED STATICALLY |
| Compilation, unit tests, instrumentation | **BLOCKED** |

---

## 10. Dead-code audit

Re-verified the previous removals; no new dead code found. `getCustomerById`
was correctly retained (it became live in BATCH 1). Nothing removed in this
pass — the remaining candidates could not be *proven* unused.

---

## 11. Negative-test results

53 existing negative tests pass, plus 31 live adversarial probes (§4).
**No permissive fallback converts a failure into a success anywhere.**

---

## 12. Browser UAT

Real Chromium, both roles, real geolocation permission.

| Section | Result |
|---|---|
| Authentication (7 checks incl. reload persistence, logout) | all pass |
| Admin pages (11 routes + FT-073 columns) | all pass, 0 console errors |
| CRUD persistence (create, reload, cancel, search) | all pass |
| Visit lifecycle (reject far, accept valid, media, duplicate, unsafe file, check-out) | all pass |
| RBAC (sidebar + 7 route redirects) | all pass |
| Design identity (9 token assertions) | all unchanged |
| Mobile 320×480 (7 pages) | no overflow |

**1 flag investigated → false positive.** The probe used a fixed sleep after
check-in; re-tested with an explicit wait, the check-out control appears
correctly. **0 product defects.**

---

## 13. Files modified in this pass

| File | Reason |
|---|---|
| `backend/app/api/v1/employees.py` | FT-073 — response model only |
| `backend/app/services/visit_service.py` | FT-074 — terminal-state guard |
| `android/.../visits/CheckOutScreen.kt` | FT-070 — remove `?: 0.0` |

## 14. Tests added

| File | Tests |
|---|---|
| `test_geo_boundary_authority.py` | 3 — FT-072 |
| `test_employee_contract.py` | 3 — FT-073 |
| `test_admin_override_integrity.py` | 7 — FT-074 |

Integration suite: **128 → 135**. All three files were confirmed to fail before
their fix and pass after.

## 15. Tests removed

**None.**

---

## 16–18. Remaining items

**OPEN (1)**
- **FT-065** (HIGH) — httpOnly refresh cookie + CSRF. Not attempted, per the
  brief. Requirements: cookie issuance on login, cookie-read on refresh,
  clear-on-logout, CSRF middleware with token endpoint, TLS + same-site
  deployment, and a body-based fallback so the Android contract still works.

**BLOCKED (5)** — FT-024, FT-025, FT-026, FT-027, FT-070: Android build
environment absent.

**DEFERRED (10)** — FT-066 requirement forms, FT-067 reports/export, FT-068
notifications (all "no endpoints exist"); FT-049–053 minor token drift and
sidebar prose; FT-035 parent item. **All remain honestly represented in the UI;
none was replaced with fabricated functionality.**

---

## 19. Ambiguities requiring product-owner decision

| ID | Question |
|---|---|
| **AMB-001** | State machine allows `IN_PROGRESS → MISSED` and `FLAGGED → MISSED`, which the spec table omits. Currently unreachable. Tighten the machine, or update the spec? |
| **AMB-002** | FT-074 now refuses to reopen a terminal visit. Should administrators instead have an audited "reopen with reason" power? Current behaviour is the conservative reading of "terminal". |
| **AMB-003** | `19_business_logic.md` §3 specifies a client-supplied `client_timestamp` for offline check-out ordering. Not implemented; the server timestamps check-out. Affects offline sync fidelity. |
| **AMB-004** | FT-053 — the visual identity prose says a navy 280 px sidebar; every mockup shows a light 240 px sidebar. Implementation follows the mockups. Unchanged pending sign-off. |

---

## 20. Final verification

```
poetry check --lock            All set!
backend unit                   88 passed
backend integration           135 passed
alembic current                c3d81b6f4a52 (head)
alembic heads                  exactly 1
migration round trip           downgrade base -> upgrade head OK (scratch DB)
app startup                    OK, scheduler running
health endpoints               /health, /api/v1/health, /api/v1/health/db, /openapi.json -> 200
npm ci                         clean
npm run typecheck              exit 0
npm run lint (--max-warnings 0) exit 0
npm run test                   68 passed
npm run build                  success
secret scan                    451 tracked files, 0 hits
browser UAT                    0 product defects
seed integrity                 users 2, employees 1, territories 1, customers 2,
                               visits 1 (COMPLETED), geo logs 1, media 0
```

**Total automated tests: 291** (88 unit + 135 integration + 68 frontend), zero
skipped.

---

## Final status

> ## REPAIR INCOMPLETE — BLOCKERS REMAIN

Unchanged from the previous report, and still accurate. Every actionable defect
reachable in this environment is fixed and evidenced, including four found in
this pass. It is not "complete" because:

- **FT-065 is OPEN** — deliberately, since cookie auth without CSRF would be a
  net regression, and the brief forbids implementing it casually.
- **5 Android defects are BLOCKED** — no JDK, Gradle or SDK, so their fixes are
  unproven. Reporting them as VERIFIED would be false.

**Recommendation:** the backend and web surfaces are demonstrably correct and
ready for the next phase. Schedule FT-065 before production deployment and
provision an Android build environment. Resolve AMB-001 through AMB-004 with
the product owner — none blocks continued development.
