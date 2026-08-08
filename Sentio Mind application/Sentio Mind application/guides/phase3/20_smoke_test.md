# FieldTrack Pro — Smoke Test (Phase 3 Close-Out)
### Quick verification before moving to Phase 4
### Revision 2 — two check items updated for the Python/FastAPI stack; all test scenarios unchanged

Not full QA (that's Phase 8) — just enough manual/Postman checking to confirm Phase 3 actually works end-to-end before building Maps/Android/Web on top of it. If any of these fail, fix before moving on — everything downstream assumes this layer works. **Every scenario below is identical to the original checklist** — the product behavior being verified didn't change, only two config-check items (27, 28) reference different tooling.

---

## 1. Auth Flow

| # | Test | Expected |
|---|---|---|
| 1 | `POST /auth/login` with valid admin credentials | 200, returns access + refresh token |
| 2 | `POST /auth/login` with wrong password | 401 |
| 3 | `POST /auth/login` 6 times with wrong password in a row | 6th attempt returns 429 (rate limit) |
| 4 | Call any protected endpoint with no `Authorization` header | 401 |
| 5 | Call any protected endpoint with an expired/garbage token | 401 |
| 6 | `POST /auth/refresh` with valid refresh token | 200, new access token issued |
| 7 | `POST /auth/logout`, then try to use the same refresh token again | Refresh fails — token was revoked |

---

## 2. Employees

| # | Test | Expected |
|---|---|---|
| 8 | `POST /employees` as ADMIN, valid payload | 201, employee + underlying user created |
| 9 | `POST /employees` as EMPLOYEE role token | 403 (role check working) |
| 10 | `PATCH /employees/{id}/deactivate`, then try logging in as that employee | Login fails — deactivation actually blocks access, not just a DB flag |
| 11 | `GET /employees/me` as an employee | Returns own profile only |

---

## 3. Customers

| # | Test | Expected |
|---|---|---|
| 12 | `POST /customers` with only an address (no lat/long) | Geocoding runs, `location` populated correctly |
| 13 | `POST /customers` with explicit lat/long | Geocoding skipped, exact coordinates stored |
| 14 | `GET /customers/{id}` as an employee with no visit to that customer | 403 (ownership-style check working, not just role check) |

---

## 4. Visits — The Critical Path

| # | Test | Expected |
|---|---|---|
| 15 | `POST /visits` scheduling employee A to customer X | 201, status `PENDING` |
| 16 | `POST /visits/{id}/check-in` from employee B (not the assigned employee) | 403 — ownership enforcement working |
| 17 | `POST /visits/{id}/check-in` with coordinates inside the geofence radius | 200, `isValid: true`, status becomes `IN_PROGRESS` |
| 18 | `POST /visits/{id}/check-in` with coordinates far outside radius | 422, `isValid: false`, `reason: OUTSIDE_RADIUS` |
| 19 | Check `geo_verification_logs` table after test 18 | A row exists — audit log is actually writing, not just returning an error |
| 20 | Repeat test 18 two more times (3 total failures) on the same visit | Visit status flips to `FLAGGED`, and a `GEO_ALERT` notification row appears for admin users |
| 21 | `POST /visits/{id}/check-in` twice with the **same** `Idempotency-Key` header | Second call returns the same result without creating a duplicate log row |
| 22 | `POST /visits/{id}/check-out` after successful check-in | 200, status becomes `COMPLETED` |
| 23 | Try `POST /visits/{id}/check-out` on a `PENDING` visit (skip check-in) | Rejected — state machine blocks invalid transition |

---

## 5. Database Sanity Checks (run directly in psql or a DB client)

| # | Check | Expected |
|---|---|---|
| 24 | `SELECT postgis_version();` | Returns a version string — extension is actually active |
| 25 | Insert a duplicate `visit_signatures` row with same `visit_id` + `signature_type` | Rejected — the unique constraint from the schema is actually in the running database |
| 26 | `SELECT * FROM geo_verification_logs LIMIT 5;` | Rows exist with realistic `distance_meters` values, not nulls |

---

## 6. Config/Startup Checks

| # | Check | Expected |
|---|---|---|
| 27 | Start the app with `JWT_SECRET` unset | App fails to start with a `pydantic.ValidationError` (not a silent fallback) — see Python Backend Setup doc Section 3 |
| 28 | Visit `/docs` (FastAPI's built-in Swagger UI) | All routers listed with correct request/response schemas |
| 29 | Check MinIO console for the dev bucket | Bucket exists, reachable (even if no files uploaded yet at this phase) |

---

## What This Smoke Test Deliberately Does NOT Cover

Saved for Phase 8 (full QA): load/performance testing, exhaustive edge-case validation (malformed payloads, boundary values), concurrent check-in race conditions, full Android/Web integration. This is purely "does the backend's core promise — server-verified, audit-logged visits — actually work" before more is built on top of it.

---

## Phase 3 — Complete (pending this checklist passing)

Once all 29 checks pass: Python Backend Setup → Authentication → Core APIs → Database Implementation → Business Logic → this smoke test. Backend is now a real, working foundation — same guarantee the original Java build gave, verified the same way.

**Next up:** Phase 4 — Maps & Location Services (Google Maps SDK, Live Location, Route Navigation, Distance Calculation) — building the pieces Android needs before Android itself gets built in Phase 6.
