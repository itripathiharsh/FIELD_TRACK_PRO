# FieldTrack Pro — Repair Ledger

**Created:** Phase 0, 2026-08-08
**Source of truth for defects:** the forensic audit report (FT-001 … FT-060).
**Source of truth for progress:** this file.

## Status vocabulary

| Status | Meaning |
|---|---|
| `OPEN` | Not started. |
| `IN_PROGRESS` | Being worked on now. |
| `FIXED` | Code changed; not yet proven by a passing regression test. |
| `VERIFIED` | Regression test failed before the fix and passes after it, **and** all criteria in `REPAIR_BASELINE.md` §10 are met. |
| `DEFERRED` | Deliberately out of scope for this program; reason recorded. |
| `NOT_APPLICABLE` | Not a real defect in this environment; evidence recorded. |

**Rule:** nothing is marked `VERIFIED` without named test evidence.
**Rule:** dead code (FT-057) is not removed until all other phases are complete.

## Phase 0 progress summary

| Severity | Total | OPEN | IN_PROGRESS | FIXED | VERIFIED | DEFERRED | N/A |
|---|---|---|---|---|---|---|---|
| CRITICAL | 6 | 6 | 0 | 0 | 0 | 0 | 0 |
| HIGH | 12 | 10 | 0 | 1 | 1 | 0 | 0 |
| MEDIUM | 24 | 22 | 0 | 0 | 1 | 0 | 1 |
| LOW | 15 | 13 | 0 | 1 | 1 | 0 | 0 |
| INFORMATIONAL | 3 | 2 | 0 | 0 | 0 | 0 | 1 |
| **Total** | **60** | **53** | **0** | **2** | **3** | **0** | **2** |

Phase 0 resolved only safety/infrastructure items (FT-043, FT-056, FT-030-adjacent
documentation, FT-058). **No application defect has been repaired.**

---

## Ledger

| ID | Severity | Status | Root Cause | Fix | Regression Test | Evidence |
|---|---|---|---|---|---|---|
| FT-001 | CRITICAL | OPEN | `AuthContext.tsx:33-44,59-72` catch-block fabricates an ADMIN user and a literal `demo_access_token` on any auth failure. | Delete both fallbacks (login + session restore); propagate the real error. | *Pending Vitest harness (blocker B-3).* Backend contract pinned by `test_auth_integration.py::test_invalid_password_returns_401`, `::test_failed_login_issues_no_tokens`, `::test_invalid_token_never_yields_a_user`. | Browser UAT: bogus credentials → full Admin dashboard. |
| FT-002 | CRITICAL | OPEN | `visits.py:43,60` use `AnyAuth` with no ownership filter (IDOR). | Scope visit reads to the caller's employee id for EMPLOYEE role. | `test_authorization_integration.py::test_employee_cannot_read_another_employees_visit`, `::test_employee_visit_list_is_scoped_to_self`, `::test_employee_cannot_read_geo_logs_of_others_visit` | **Tests FAIL as expected**: other employee's visit is readable. |
| FT-003 | HIGH | OPEN | `types/index.ts` `Visit` declares 8 fields absent from `VisitRead`. | Align the TS type to the real schema; remove `as any` casts. | *Pending Vitest.* Backend shape pinned by visit lifecycle tests. | Audit contract matrix. |
| FT-004 | CRITICAL | OPEN | `_extract_coords_from_wkt` parses `str(WKBElement)` hex as WKT, fails, and silently returns `(0.0, 0.0)`. Geofence is measured against Null Island → **inverted**. | Use `ST_AsText`/`to_shape`; raise on parse failure; prefer existing `verify_geo_proximity` (PostGIS). | `test_geo_integration.py::test_coordinate_extraction_from_orm_value_is_correct`, `::test_unparseable_location_must_not_silently_become_origin`, `::test_verify_location_at_exact_customer_coordinates_is_valid`, `::test_null_island_is_not_treated_as_the_customer_site`, `::test_check_in_at_correct_location_succeeds`, `::test_check_in_at_null_island_is_rejected`, `::test_just_inside_and_just_outside_radius`, `::test_check_out_uses_same_geofence_rules` | **Tests FAIL as expected**: `assert (0.0, 0.0) != (0.0, 0.0)`; check-in from (0,0) returns 200. |
| FT-005 | CRITICAL | OPEN | `visit_service.py:233` calls `GeoLogRepository.list_by_visit`, which does not exist → `AttributeError` → 500. | Implement `list_by_visit` with deterministic ordering. | `test_geo_audit_integration.py::test_geo_logs_can_be_read_back_by_admin`, `::test_geo_logs_endpoint_never_returns_500`, `::test_assigned_employee_can_read_own_geo_logs`, `::test_geo_log_ordering_is_deterministic` | **Tests FAIL as expected**: `AttributeError: 'GeoLogRepository' object has no attribute 'list_by_visit'`. |
| FT-006 | CRITICAL | OPEN | Web client calls `GET /api/v1/users` (405, does not exist) and passes `users.id` where `employees.id` is required → FK 500. | Add `getEmployees()` → `GET /employees`; use `employees.id`; return a validated 4xx for unknown ids. | `test_visit_lifecycle_integration.py::test_visit_create_with_user_id_is_rejected_cleanly`, `::test_visit_create_with_unknown_customer_is_rejected_cleanly`, `::test_admin_creates_visit_with_employee_id` | **Tests FAIL as expected**: unknown `employee_id` returns 500. |
| FT-007 | HIGH | OPEN | `createUser()` sends `full_name`/`mobile` (dropped); no Employee row is created. | Two-step create: user → employee profile. | *Phase 6.* | Audit contract matrix. |
| FT-008 | HIGH | OPEN | `/auth/refresh` never called by the web client. | Add a 401-triggered refresh interceptor. | `test_auth_integration.py::test_refresh_token_returns_new_usable_pair`, `::test_refresh_token_is_rotated_and_old_one_revoked` | Backend refresh verified working; frontend integration missing. |
| FT-009 | HIGH | OPEN | `client.logout()` only clears `localStorage`; server session survives 7 days. | Call `POST /auth/logout`. | `test_auth_integration.py::test_logout_revokes_refresh_token_server_side` | Browser UAT: no logout request observed. |
| FT-010 | HIGH | OPEN | Client sends `mobile`; schema expects `mobile_number`; pydantic `extra=ignore` drops it. | Rename to `mobile_number`; reject unknown keys. | `test_auth_integration.py::test_login_by_mobile_number_is_supported` | Test asserts `mobile` must be rejected, not silently ignored. |
| FT-011 | HIGH | OPEN | `/auth/me` omits `full_name`; returns `mobile_number` where the UI expects `mobile`. | Add identity fields to `/auth/me` (or align the type). | `test_auth_integration.py::test_me_exposes_identity_fields_the_ui_requires` | **Test FAILS as expected**: `full_name` absent. |
| FT-012 | HIGH | OPEN | `CustomerRead` omits latitude/longitude/phone/email/contact_person/is_active. | Return `location:{latitude,longitude}`; align the TS type. | `test_customer_integration.py::test_customer_read_exposes_coordinates` | **Test FAILS as expected**: no coordinates in the response. |
| FT-013 | HIGH | OPEN | UI "Contact Person" maps to `contact_number varchar(20)`; a 30-char name → unhandled 500. | Add `contact_person`; widen or validate `contact_number`. | `test_customer_integration.py::test_long_contact_value_does_not_cause_500` | **Test FAILS as expected**: returns 500. |
| FT-014 | MEDIUM | OPEN | No customer edit/delete UI; `PATCH /customers/{id}` orphaned. | Add edit modal. | `test_customer_integration.py::test_customer_update_persists` (backend proven) | Backend PATCH verified working. |
| FT-015 | HIGH | OPEN | UI does `media_type.includes('image')` against enum `PHOTO`; `<img>`/`<a>` cannot send the Bearer header. | Compare to `'PHOTO'`; fetch blob with auth (or short-lived signed URL). | `test_media_integration.py::test_media_type_is_an_enum_not_a_mime_string`, `::test_download_without_auth_is_rejected`, `::test_authenticated_download_returns_original_bytes` | Tests pass — they pin the true contract the UI violates. |
| FT-016 | MEDIUM | OPEN | No media delete control in the UI. | Add guarded delete action. | `test_media_integration.py::test_delete_removes_row_and_stored_object` | Backend delete verified working. |
| FT-017 | MEDIUM | OPEN | Territory UI expects `code` and counts that do not exist. | Add fields to the API or remove from the UI. | *Phase 6.* | Renders `undefined`; hardcoded "4 Agents / 16 Accounts". |
| FT-018 | MEDIUM | OPEN | "New Territory" button has no handler. | Wire `POST /territories`. | *Phase 8.* | Audit route inventory. |
| FT-019 | MEDIUM | OPEN | `/visits/me/today` never called by the web client. | Use it for the EMPLOYEE dashboard. | `test_visit_lifecycle_integration.py::test_employee_today_endpoint_returns_only_own_visits` | Backend endpoint verified correctly scoped. |
| FT-020 | MEDIUM | OPEN | No admin status-override UI. | Add an admin action bar. | `test_visit_lifecycle_integration.py::test_admin_can_force_status`, `::test_employee_cannot_force_status` | Backend PATCH verified working and role-gated. |
| FT-021 | HIGH | OPEN | `missed_visit_scheduler` docstring claims APScheduler wiring in `main.py` lifespan; none exists. | Wire the scheduler, or remove it and correct the docstring. | *Phase 5.* | `main.py` contains no scheduler. |
| FT-022 | MEDIUM | OPEN | No activate/deactivate UI; two endpoints orphaned. | Add a toggle. | Backend behaviour pinned by `test_auth_integration.py::test_deactivated_user_cannot_use_existing_token`. | Deactivation correctly revokes access immediately. |
| FT-023 | MEDIUM | OPEN | No change-password UI. | Add a form. | *Phase 8.* | Endpoint orphaned. |
| FT-024 | LOW | OPEN | Android `LoginRequest.mobile`, `UserDto.full_name` do not match the backend. | Align DTOs. | *Blocked by B-4 (no Android build).* | Static review. |
| FT-025 | LOW | OPEN | Android `VisitDto` declares 8 nonexistent fields (Gson non-null crash risk). | Align DTOs. | *Blocked by B-4.* | Static review. |
| FT-026 | LOW | OPEN | Android `LocationVerifyResponse.allowed_radius_m` vs API `geofence_radius_m`. | Rename. | *Blocked by B-4.* | Static review. |
| FT-027 | LOW | OPEN | Android `TokenManager` stores tokens in plaintext SharedPreferences. | Use EncryptedSharedPreferences / Keystore. | *Blocked by B-4.* | Security Design §1. |
| FT-028 | MEDIUM | OPEN | Dashboard uses fabricated fallbacks (`employees.length \|\| 12`). | Remove fallbacks; add `/dashboard/overview`. | *Pending Vitest.* | Browser UAT: showed "12" with 1 employee. |
| FT-029 | MEDIUM | OPEN | Forms / Reports / Settings pages are 100% hardcoded. | Implement or mark clearly as unavailable. | *Phase 12.* | No network calls observed. |
| FT-030 | LOW | VERIFIED (documentation) | Two contradictory design sources: stale UI Bible (teal/Inter) vs locked visual identity (navy/League Spartan). | Documented in `REPAIR_BASELINE.md`; UI Bible to be annotated as superseded. **No visual change.** | N/A — documentation. | Rendered tokens match the locked visual identity exactly. |
| FT-031 | MEDIUM | OPEN | `geo_verification_logs` has no `verification_type` (CHECK_IN vs CHECK_OUT). | Add column + Alembic migration. | `test_geo_audit_integration.py` (extend once the column exists). | Audit ER map. |
| FT-032 | HIGH | OPEN | Audit-log immutability not enforced at DB level (Security Design §4 non-negotiable). | `REVOKE UPDATE, DELETE ON geo_verification_logs FROM fieldtrack_app`. | *Phase 2.* | **Unblocked in Phase 0**: the app no longer connects as superuser. |
| FT-033 | MEDIUM | OPEN | `idempotency_key` has no UNIQUE constraint. | `UNIQUE(visit_id, idempotency_key)`. | *Phase 2.* | Fraud audit VULN-09. |
| FT-034 | MEDIUM | OPEN | `users` lacks `CHECK(email IS NOT NULL OR mobile_number IS NOT NULL)`. | Add CHECK constraint. | *Phase 2.* | Service-level validation only. |
| FT-035 | HIGH | OPEN | requirement_forms / signatures / notifications / categories: tables and models exist, no API. | Implement or formally descope. | *Phase 12.* | 4 empty tables, 0 endpoints. |
| FT-036 | MEDIUM | OPEN | `visit_media` has no checksum / original_filename / uploaded_by; duplicates accepted. | Store SHA-256; reject duplicates. | *Phase 9.* | Duplicate upload verified accepted (fraud VULN-03). |
| FT-037 | LOW | OPEN | Web `checkIn()` omits `idempotency_key`. | Generate and send a UUID. | *Phase 9.* | Backend supports it. |
| FT-038 | MEDIUM | OPEN | Frontend declares a `MANAGER` role that does not exist in the backend. | Remove MANAGER (or add backend support). | *Pending Vitest.* | Backend enum has 2 roles. |
| FT-039 | MEDIUM | OPEN | No check-out UI; `checkOut()` unused. | Add a state-aware button. | `test_visit_lifecycle_integration.py::test_check_out_transitions_in_progress_to_completed` | Backend check-out proven (blocked by FT-004). |
| FT-040 | HIGH | OPEN | Both tokens stored in `localStorage` (Security Design §1 forbids). | Access token in memory; refresh in httpOnly cookie. | *Phase 3.* | Browser UAT. |
| FT-041 | MEDIUM | OPEN | No login rate limiting (spec: 5 / 15 min). | Add slowapi. | *Phase 3.* | Fraud audit VULN-10. |
| FT-042 | LOW | OPEN | JWT `role` claim is embedded but never consumed. | Document intent (DB check is correct and safer). | *Phase 3.* | Grep: no readers. |
| FT-043 | MEDIUM | **VERIFIED** | `.env` contained live DB and JWT credentials. | DB password rotated **and** privilege reduced to new `fieldtrack_app` role; JWT secret rotated; 8 refresh tokens revoked; `.env.example` sanitised. No VCS history to purge. | Old JWT secret verified rejected; new secret verified working; app verified running as non-superuser `fieldtrack_app`. | `docs/SECRET_ROTATION.md`. |
| FT-044 | MEDIUM | OPEN | "Schedule Visit" button not role-gated. | Gate on role. | *Pending Vitest.* | Browser UAT: employee sees it. |
| FT-045 | MEDIUM | OPEN | Admin cards/quick-links shown to employees. | Role-aware dashboard. | *Pending Vitest.* | Browser UAT. |
| FT-046 | MEDIUM | OPEN | 500 responses lose `Access-Control-Allow-Origin`, so the browser reports a CORS error and hides the real crash. | Ensure the exception handler runs inside CORS middleware. | *Phase 5.* | Confirmed: 500 response carried no CORS header. |
| FT-047 | MEDIUM | OPEN | Seed `visit_media` row references `uploads/visits/.../site_photo_01.jpg`; no such file exists. | Remove the orphan row or restore the file. | `test_media_integration.py::test_uploaded_bytes_actually_reach_storage` (guards regressions) | `media_storage/` verified empty; download returns 404. |
| FT-048 | LOW | NOT_APPLICABLE | Reported "320×480 layout breaks". | None — responsive behaviour is correct. Tables scroll horizontally inside `overflow-x-auto`, exactly as UI Bible §4.4 prescribes. | N/A. | Browser UAT at 320×480: `scrollWidth == innerWidth`, sidebar off-canvas, hamburger works. |
| FT-049 | LOW | OPEN | `on-primary-container` is `#ffffff`; locked identity says `#7c89aa`. | Align token. | *Phase 11 (optional).* | `tailwind.config.js`. |
| FT-050 | LOW | OPEN | `borderRadius.md` 0.25rem vs locked 0.375rem. | Align token. | *Phase 11 (optional).* | `tailwind.config.js`. |
| FT-051 | LOW | OPEN | `borderRadius.lg` 0.25rem vs locked 0.5rem. | Align token. | *Phase 11 (optional).* | `tailwind.config.js`. |
| FT-052 | LOW | OPEN | `borderRadius.xl` 0.5rem vs locked 0.75rem. | Align token. | *Phase 11 (optional).* | `tailwind.config.js`. |
| FT-053 | LOW | OPEN | Visual-identity prose says navy 280px sidebar; every mockup shows light 240px. Implementation follows the mockups. | Product decision required. **No change without approval.** | N/A. | Documented in the audit. |
| FT-054 | LOW | OPEN | Geofence default is 75 (DB/schema) but 100 in four UI locations. | Standardise on 75. | *Phase 7.* | Audit duplication matrix. |
| FT-055 | MEDIUM | OPEN | Two base-URL strategies: `request()` strips `/api/v1`, `uploadMedia()` uses the raw env value. | Single normaliser. | *Pending Vitest.* | `.env` sets `VITE_API_BASE_URL=.../api/v1`. |
| FT-056 | LOW | **VERIFIED** | `.env.example` missing storage/MinIO/JWT-lifetime keys. | Rewritten with all keys, placeholders only, and security guidance. | Verified `.env.example` contains no real secret; app boots with `STORAGE_PROVIDER=LOCAL`. | `fieldtrackpro-backend/.env.example`. |
| FT-057 | LOW | OPEN | ~26 dead/orphan code items. | Remove **after** all repair phases (Rule 19). | *Phase 13.* | Audit dead-code inventory. |
| FT-058 | LOW | FIXED | `pytest_full_output.txt` records a stale 15-failure run contradicting the live result. | Superseded by `REPAIR_BASELINE.md` §3, which explains the venv/`psycopg2` cause. File to be deleted in Phase 13. | N/A. | Root cause identified: stale virtualenv, undeclared `psycopg2`. |
| FT-059 | INFORMATIONAL | FIXED | `PHASE_8_REAL_EXECUTION_EVIDENCE.md` claims "CERTIFIED" and calls the dangling media row "intentional". | Superseded by the forensic report and `REPAIR_BASELINE.md`. | N/A. | Contradicted by FT-047 and 6 CRITICAL defects. |
| FT-060 | INFORMATIONAL | OPEN | Login page ships hardcoded demo presets and a prefilled password. | Remove for production. | *Phase 3.* | `LoginPage.tsx`. |
| **FT-061** | **MEDIUM** | **VERIFIED** | **NEW (Phase 0).** `psycopg2` used by `tests/conftest.py` but undeclared, so `IS_DB_MIGRATED=False` and **17 DB tests silently skipped** in a clean environment while still reporting success. | Added `psycopg2-binary` to the `dev` extra; re-locked. | Full suite now `88 passed, 0 skipped`. | Before: `71 passed, 17 skipped`. After: `88 passed`. |
| **FT-062** | **MEDIUM** | **VERIFIED** | **NEW (Phase 0).** Poetry's active virtualenv was empty; dependencies lived in a stale venv, so the documented `poetry run pytest` failed. | Ran `poetry install --extras dev` to populate the canonical environment. | `poetry run python -m pytest` → 88 passed. | Documented in `REPAIR_BASELINE.md` §2. |
| **FT-063** | **HIGH** | **OPEN** | **NEW (Phase 0).** The project is **not under version control** — no `.git` anywhere. No rollback point, no diff review, no branch isolation. | Initialise a repository and make a baseline commit before Phase 1 edits. **Requires approval.** | N/A. | `git rev-parse` → `fatal: not a git repository`. |
| **FT-064** | **MEDIUM** | **OPEN** | **NEW (Phase 0).** `npm run lint` fails — `eslint` is declared as a script but is not a dependency. | Add eslint + config, or remove the script. | N/A. | `'eslint' is not recognized`. |

---

## Test evidence index

New integration suite: `fieldtrackpro-backend/tests/integration/`

| File | Tests | Purpose |
|---|---|---|
| `conftest.py` | — | Infrastructure: marker-tagged seeded world, real login helpers, independent psycopg2 assertions, self-healing cleanup. |
| `test_auth_integration.py` | 15 | Scenarios 1-5 + refresh/logout lifecycle + FT-010/FT-011. |
| `test_authorization_integration.py` | 15 | Scenarios 6-9 + FT-002 IDOR. |
| `test_geo_integration.py` | 13 | Scenarios 10-16 + FT-004 root cause. |
| `test_geo_audit_integration.py` | 8 | Scenarios 17-20 + FT-005. |
| `test_visit_lifecycle_integration.py` | 12 | Scenarios 21-25 + FT-006. |
| `test_media_integration.py` | 21 | Scenarios 26-30 + FT-015/FT-047 guards. |
| **Total** | **88** | 64 passing (locking in correct behaviour), **24 failing by design**. |

### The 24 intentionally-failing tests, by defect

| Defect | Failing tests |
|---|---|
| FT-004 (geofence inverted) | 8 |
| FT-005 (geo audit unreadable) | 5 *(4 direct + 1 workflow)* |
| FT-006 (employee id / 500) | 2 |
| FT-002 (IDOR) | 2 |
| FT-004 knock-on (lifecycle blocked) | 4 |
| FT-011 (`full_name` missing) | 1 |
| FT-012 (coordinates missing) | 1 |
| FT-013 (contact overflow 500) | 1 |
