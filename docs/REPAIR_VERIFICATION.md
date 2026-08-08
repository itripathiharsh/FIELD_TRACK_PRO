# FieldTrack Pro — Repair Verification

**Programme:** forensic audit → Phase 0 baseline → repair batches 0–I
**Baseline commit:** `18e9088` (tag `phase0-baseline`)
**Head at verification:** `aca5d1b`

Status vocabulary is defined in `REPAIR_LEDGER.md`. **BLOCKED is never reported
as VERIFIED.** A defect is VERIFIED only where a named test failed before the
fix and passes after it, or where objective runtime evidence is recorded.

---

## 1. Verification commands

```bash
# Backend
cd fieldtrackpro-backend
poetry check --lock
poetry install --extras dev
poetry run python -m pytest tests --ignore=tests/integration -q   # unit
poetry run python -m pytest tests/integration -q                  # integration
poetry run alembic current && poetry run alembic heads
poetry run python -c "from app.main import app; app.openapi()"     # OpenAPI

# Frontend
cd fieldtrackpro-web
npm ci
npm run typecheck
npm run lint          # --max-warnings 0
npm run test
npm run build

# Android
cd fieldtrackpro-android
./gradlew assembleDebug        # BLOCKED - see section 6
```

---

## 2. Test matrix

| Suite | Phase 0 baseline | Final | Delta |
|---|---|---|---|
| Backend unit | 88 passed | **88 passed** | maintained |
| Backend integration | 64 passed / **24 failed** | **122 passed / 0 failed** | +58 tests, all green |
| Frontend tests | **did not exist** | **68 passed** | +68 |
| Frontend lint | **crashed** (eslint absent) | **0 errors, 0 warnings** | fixed |
| Frontend typecheck | passed (hiding errors behind `as any`) | **passed, no `as any`** | strengthened |
| Frontend build | success | success | maintained |
| **Total automated tests** | **88** | **278** | **+190** |

No test is skipped. No tolerant multi-status assertion is used on a success path.

---

## 3. Per-defect verification

### CRITICAL

| FT | Defect | Root cause | Repair | Test evidence | Status |
|---|---|---|---|---|---|
| **FT-001** | Any credential logged in as ADMIN | `AuthContext` catch-block fabricated a user + `demo_access_token`; session restore did the same | Both fallbacks deleted; backend is sole authority; failures propagate | `AuthContext.test.tsx` (11) — 8 failed before, all pass. Browser: bogus creds stay on `/login`, `localStorage` empty | **VERIFIED** |
| **FT-002** | IDOR — any employee could read any visit | `AnyAuth` with no ownership filter on 2 read paths | Ownership enforced in service layer via one shared helper; employee's `employee_id` filter overridden with their own | `test_authorization_integration.py` (15) incl. `test_employee_cannot_read_another_employees_visit` | **VERIFIED** |
| **FT-004** | Geofence **inverted** — correct location rejected, (0,0) accepted | `str(WKBElement)` parsed as WKT → silent `(0.0,0.0)` | Proper WKB/WKT/EWKT decode that **raises** on failure; PostGIS `ST_Distance` is the source of truth; no Haversine fallback | `test_geo_integration.py` (13). Browser: site→valid 0.0 m; (0,0)→rejected 8 672 km; 290 km→rejected | **VERIFIED** |
| **FT-005** | Geo audit unreadable (500 on every read) | `GeoLogRepository.list_by_visit` never implemented | Implemented with deterministic ordering | `test_geo_audit_integration.py` (9). Browser: 200, no 500 | **VERIFIED** |
| **FT-006** | Employee assignment impossible | Client called non-existent `GET /users` (405); passed `users.id` where `employees.id` required | Client uses `GET /employees`; backend validates ids → 404 not 500 | `test_visit_lifecycle_integration.py`, `VisitsPage.test.tsx`. Browser: dropdown populated, visit created 201 | **VERIFIED** |
| **FT-003** | 8 invented `Visit` fields forced `as any` | Frontend types diverged from schemas | Types rewritten to mirror real schemas | `npm run typecheck` clean; `lint --max-warnings 0` passes with zero `as any` | **VERIFIED** |

### HIGH

| FT | Defect | Repair | Test evidence | Status |
|---|---|---|---|---|
| **FT-007** | New user got no employee profile | Two-step create (user → employee) | `EmployeesPage` rewrite; browser: employee list populated | **VERIFIED** |
| **FT-008** | No token refresh; session died at 15 min | Refresh-on-401 interceptor | `client.test.ts` refresh suite; `test_auth_integration.py` rotation tests | **VERIFIED** |
| **FT-009** | Logout left server session alive 7 days | `POST /auth/logout` called; token revoked | `test_logout_revokes_refresh_token_server_side`; `client.test.ts` | **VERIFIED** |
| **FT-010** | Mobile login impossible (`mobile` vs `mobile_number`) | Client corrected; schema `extra="forbid"` | `test_login_by_mobile_number_is_supported`; `client.test.ts` | **VERIFIED** |
| **FT-011** | `/auth/me` lacked `full_name` | `CurrentUserRead` adds `full_name`, `territory_id`, `employee_id` | `test_me_exposes_identity_fields_the_ui_requires` | **VERIFIED** |
| **FT-012** | Customer coordinates never returned | `CustomerRead.location` added | `test_customer_read_exposes_coordinates`; `CustomersPage.test.tsx`; browser | **VERIFIED** |
| **FT-013** | 30-char contact name → unhandled 500 | `contact_person` column added; lengths bounded | `test_long_contact_value_does_not_cause_500`; browser: saves and persists | **VERIFIED** |
| **FT-015** | Media preview/download 403 | Enum compared correctly; blob fetched with auth | `test_media_integration.py`; browser: thumbnail renders | **VERIFIED** |
| **FT-021** | Missed-visit scheduler never wired | APScheduler cron `*/15`, 2 h grace, duplicate-guarded | 6 tests incl. grace window, idempotency, single-job registration | **VERIFIED** |
| **FT-032** | Audit log mutable by app | `REVOKE UPDATE, DELETE, TRUNCATE` from `fieldtrack_app` | DB: grants are `INSERT, SELECT` only; UPDATE/DELETE refused | **VERIFIED** |
| **FT-035** | 4 spec'd modules absent | Split into FT-066/067/068; misleading UI removed | See DEFERRED | **DEFERRED** |
| **FT-040** | Access token in `localStorage` | Access token now **in memory only** | `client.test.ts` FT-040 suite; browser: only refresh token persisted | **PARTIAL** → remainder = FT-065 |

### MEDIUM / LOW (abridged — all verified unless noted)

| FT | Repair | Evidence | Status |
|---|---|---|---|
| FT-014 | Customer edit UI | `CustomersPage.test.tsx` edit tests; browser | **VERIFIED** |
| FT-016 | Media delete control | `MediaThumbnail`; `test_delete_removes_row_and_stored_object` | **VERIFIED** |
| FT-017 | Real territory data, no fake counts | Browser: "1 Field Agent / 1 Account", no `undefined` | **VERIFIED** |
| FT-018 | Territory create wired | `TerritoriesPage` create modal | **VERIFIED** |
| FT-019 | Employee uses `/visits/me/today` | `DashboardPage.test.tsx` | **VERIFIED** |
| FT-020 | Admin status override UI | `VisitDetailsPage` admin bar; backend tests | **VERIFIED** |
| FT-022 | Activate/deactivate + token revocation | `test_deactivation_revokes_refresh_tokens` | **VERIFIED** |
| FT-023 | Change-password UI + session revocation | 6 tests incl. other-device revocation; browser | **VERIFIED** |
| FT-028 | Fabricated metrics removed | `DashboardPage.test.tsx` asserts 12/48/24 absent | **VERIFIED** |
| FT-029 | Fabricated Reports/Forms/Settings content removed | Browser: no 96.4%, no fake templates, no fake save | **VERIFIED** |
| FT-031 | `verification_type` column | Migration `a1c4e77b9d21`; audit tests | **VERIFIED** |
| FT-033 | Unique `(visit_id, idempotency_key)` | Partial unique index present | **VERIFIED** |
| FT-034 | `CHECK(email OR mobile_number)` | Constraint present; 0 violating rows | **VERIFIED** |
| FT-036 | Checksum, dedup, tamper detection | `test_media_integrity.py` (13); browser 409 | **VERIFIED** |
| FT-037 | Idempotency key sent on check-in | `VisitDetailsPage` sends UUID | **VERIFIED** |
| FT-038 | MANAGER role removed | Types + UI; `App.test.tsx` | **VERIFIED** |
| FT-039 | Check-out control | Browser: full lifecycle to COMPLETED | **VERIFIED** |
| FT-041 | Rate limiting 5/15 min | 7 tests; browser `401×5 → 429` | **VERIFIED** |
| FT-042 | JWT `role` claim documented (DB check is authoritative) | Code comment; `require_role` reads DB | **VERIFIED** |
| FT-043 | Secrets rotated, privilege reduced | `SECRET_ROTATION.md`; old JWT rejected | **VERIFIED** |
| FT-044/045 | Role-gated UI controls | `VisitsPage`/`DashboardPage` tests; browser | **VERIFIED** |
| FT-046 | CORS preserved on 500 | `test_cors_headers_present_on_unhandled_500`; browser: 0 CORS errors | **VERIFIED** |
| FT-047 | Orphan media row removed | `test_no_orphaned_media_rows_exist` | **VERIFIED** |
| FT-054 | Geofence default 75 | `CustomersPage` form default | **VERIFIED** |
| FT-055 | Single base-URL normaliser | `client.test.ts` | **VERIFIED** |
| FT-056 | `.env.example` completed | All keys, placeholders only | **VERIFIED** |
| FT-057 | Dead code removed | 11 items; suites green after | **VERIFIED** |
| FT-058/059 | Stale artefacts superseded/deleted | `pytest_full_output.txt` removed | **VERIFIED** |
| FT-060 | Demo presets removed | `App.test.tsx`; browser: 0 role tabs | **VERIFIED** |
| FT-061 | `psycopg2` declared | 88 passed, 0 skipped | **VERIFIED** |
| FT-062 | Poetry env repaired | `poetry run pytest` works | **VERIFIED** |
| FT-063 | Git initialised | Commit `18e9088`, tag `phase0-baseline` | **VERIFIED** |
| FT-064 | ESLint installed | `npm run lint` exit 0 | **VERIFIED** |
| FT-069 | Dashboard fetched before auth resolved | Waits for auth | `DashboardPage.test.tsx` | **VERIFIED** |
| FT-071 | Dead search box + fake notification dot removed | Header cleaned | **VERIFIED** |
| FT-030 | Design-source conflict documented | No code change | **VERIFIED (doc)** |
| FT-048 | Responsive claim disproved | Browser 320×480: no overflow | **NOT_APPLICABLE** |
| FT-049–053 | Minor token drift / sidebar prose | Not changed — requires product sign-off | **DEFERRED** |

### Android — BLOCKED (never VERIFIED)

| FT | Repair applied (static only) | Status |
|---|---|---|
| FT-024 | `LoginRequest.mobile_number`; `UserDto` matches `CurrentUserRead` | **BLOCKED** |
| FT-025 | `VisitDto`/`CustomerDto` rewritten against real schemas; 3 screens updated | **BLOCKED** |
| FT-026 | `geofence_radius_m` (was `allowed_radius_m`) | **BLOCKED** |
| FT-027 | `EncryptedSharedPreferences` + Keystore; legacy store purged | **BLOCKED** |
| FT-070 | Removed `?: 0.0` coordinate coercion | **BLOCKED** |

---

## 4. Security verification

| Control | Evidence | Result |
|---|---|---|
| Password hashing | bcrypt cost 12 | PASS |
| Failed login | 401, no tokens issued, no session | PASS |
| Forged / expired / tampered JWT | 401 | PASS |
| Old (pre-rotation) JWT secret | rejected | PASS |
| Deactivated user with valid token | 401 immediately | PASS |
| Employee → admin routes (×4 API) | 403 | PASS |
| Employee → another's visit / geo-logs / media | 403 or 404 | PASS |
| Employee visit list scoping | own visits only | PASS |
| Unauthenticated → 6 protected routes | 401/403 | PASS |
| Rate limiting | `401×5 → 429`; per-identifier; sliding window; cannot grant access | PASS |
| Password change | revokes other sessions | PASS |
| Audit immutability | UPDATE/DELETE refused at DB level | PASS |
| File validation | `.exe`, empty, JS, HTML-as-JPEG rejected (415/400) | PASS |
| Path traversal | 400 | PASS |
| Media cross-employee download | 403 | PASS |
| Media tamper detection | checksum mismatch → refuse to serve | PASS |
| CORS on 500 | header preserved, internals not leaked | PASS |
| Access token storage | memory only | PASS |
| Secrets in tracked files | 0 occurrences across 426 files | PASS |

---

## 5. Database verification

- Alembic: **one head**, `c3d81b6f4a52`, current == head, no drift.
- Migration chain: `74454433b4c6 → 02bc15442e20 → a1c4e77b9d21 → b7f2a91c5e40 → c3d81b6f4a52`.
- Referential integrity: **0 orphans** across 9 checks.
- Constraints present: `ck_users_identity_present`, `uq_visit_media_content`,
  `uq_visit_media_storage_key`, `uq_visit_signature`.
- Indexes present: `idx_customers_location` (GIST), `idx_visits_check_in_location`,
  `uq_geo_log_visit_idempotency`, `ix_visit_media_checksum`.
- PostGIS 3.5, all geographies SRID 4326.
- App role grants on `geo_verification_logs`: **INSERT, SELECT only**.
- Seed integrity after all testing and UAT: users 2, employees 1, territories 1,
  customers 2, visits 1, geo_verification_logs 1, visit_media 0
  (the FT-047 orphan was legitimately removed). `media_storage/` holds only `.gitkeep`.

---

## 6. Android verification — BLOCKED

**Attempted:**
```
PS> .\gradlew.bat assembleDebug
ERROR: The term '.\gradlew.bat' is not recognized...
PS> gradle assembleDebug
ERROR: The term 'gradle' is not recognized...
```

**Environment state:**

| Requirement | Status |
|---|---|
| `gradlew` / `gradlew.bat` | **absent** |
| `gradle/wrapper/gradle-wrapper.jar` | **absent** |
| `gradle/wrapper/gradle-wrapper.properties` | added by this programme (Gradle 8.9 for AGP 8.7.2) |
| JDK (`java` on PATH, `JAVA_HOME`) | **absent / unset** |
| Gradle on PATH | **absent** |
| Android SDK (`ANDROID_HOME`) | **unset** |

**Required to verify:** JDK 17+, Android SDK (API 35), and
`gradle wrapper --gradle-version 8.9` run once to generate the wrapper JAR and
scripts (binaries that cannot responsibly be hand-authored).

**Therefore:** FT-024, FT-025, FT-026, FT-027 and FT-070 are **BLOCKED**. Their
fixes were derived by comparing every DTO field against the live OpenAPI schema,
but no compilation or test has been run. **No Android claim of success is made.**

---

## 7. Browser UAT

Real Chromium against the running stack. Full transcript in commit `6c9aa6e`.
Both roles, full lifecycle with a real geolocation fix
(check-in → upload → duplicate refused → check-out → COMPLETED), mobile
320×480, and design-token comparison. **1 reported finding investigated and
proven a false positive** (probe opened a COMPLETED visit and used a stale
locator); re-tested correctly, all controls present. **0 product defects.**

Design identity confirmed **unchanged**: body `#fbf8fb` / Libre Baskerville;
h1 `#000a24` / League Spartan 32 px; nav active `#14213d` on `#ffa515`;
primary button `#ffa515`, radius 4 px.

---

## 8. Outstanding items

| FT | Severity | Status | Reason |
|---|---|---|---|
| FT-065 | HIGH | **OPEN** | httpOnly refresh cookie + CSRF. Needs backend cookie issuance, CSRF middleware, TLS, and an Android-compatible contract. Doing it without CSRF would be a net regression (RD-003). |
| FT-066 | MEDIUM | **DEFERRED** | Requirement forms module — no endpoints exist; new feature work. |
| FT-067 | MEDIUM | **DEFERRED** | Reports module (`/reports/*`, CSV/PDF export) — new feature work. |
| FT-068 | MEDIUM | **DEFERRED** | Notifications (`/notifications/me`) — new feature work. |
| FT-024–027, FT-070 | HIGH/MED/LOW | **BLOCKED** | Android build environment absent. |
| FT-049–053 | LOW | **DEFERRED** | Minor design-token drift; requires product sign-off, and rule 9 forbids unrequested visual change. |

Fraud-audit items VULN-01 (hardware attestation), VULN-04 (minimum dwell time),
VULN-05 (evidence-required check-out) and VULN-06 (schedule window) remain
product-policy decisions, not defects; VULN-03 (photo reuse) and VULN-09
(duplicate logs) were closed by FT-036 and FT-033.
