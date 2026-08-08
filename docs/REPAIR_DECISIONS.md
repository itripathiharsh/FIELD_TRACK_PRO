# FieldTrack Pro — Repair Decisions

Decisions taken during the repair program where the specification, the existing
implementation, or the environment conflicted. Recorded per repair rule 14 so no
scope change is silent.

---

## RD-001 — Application database role separated from the schema owner

**Context:** FT-043 (secret rotation) and FT-032 (audit immutability).

**Conflict:** The application connected as the PostgreSQL superuser `postgres`.
Security Design §4 requires `geo_verification_logs` to be insert-only *at the
database level*. A superuser bypasses all GRANT/REVOKE, so that requirement was
unimplementable as configured.

**Decision:** Created a dedicated least-privilege role `fieldtrack_app` for
runtime, and added `MIGRATION_DATABASE_URL` for Alembic, which legitimately
needs table ownership for DDL and GRANT/REVOKE.

**Consequence:** Deployment now requires two credentials rather than one. This
is documented in `.env.example`. The superuser password itself was deliberately
**not** rotated: it is a machine-wide account used by other local projects, and
the application no longer uses it. Flagged for the environment owner.

**Status:** Implemented and verified. The app role is refused UPDATE and DELETE
on the audit table while retaining SELECT/INSERT.

---

## RD-002 — Test fixtures use a privileged teardown connection

**Context:** FT-032 made `geo_verification_logs` insert-only for the application
role. Integration fixtures need to delete their own audit rows.

**Options considered:**
1. Weaken the constraint so tests can clean up — rejected; it would defeat the
   control the test exists to prove.
2. Leave test data behind — rejected; violates the "seed data unchanged"
   guarantee.
3. Clean up as the schema owner.

**Decision:** Option 3. `db_cursor(privileged=True)` connects as the owner and
is used **only** in fixture setup/teardown. Every assertion about application
behaviour still runs through the restricted role, which is what the
FT-032 test explicitly verifies.

**Status:** Implemented. Permitted by repair rule 11.

---

## RD-003 — FT-040: access token storage

**Context:** Security Design §1 states: *"Web: access token in memory only
(never localStorage — XSS risk); refresh token in httpOnly, Secure,
SameSite=Strict cookie."*

**Conflict:** The httpOnly-cookie half of that requirement cannot be implemented
by the frontend alone. It requires the backend to:
* set the refresh cookie on `POST /auth/login`,
* read the refresh token from the cookie on `POST /auth/refresh`,
* clear it on `POST /auth/logout`,
* add CSRF protection, because cookie-borne credentials are sent automatically
  and the API becomes CSRF-eligible the moment it trusts a cookie,
* and it presumes HTTPS + same-site deployment, which the current dev setup
  (`localhost:5173` → `localhost:8000`, plain HTTP) does not satisfy.

The Android client also uses the same `/auth/*` contract and does not use
cookies, so the endpoints must continue to accept a body-supplied refresh token.

**Decision:** Implement the part that is unambiguously correct and carries no
architectural risk, and record the remainder honestly rather than half-building
a cookie scheme without CSRF defence:

* **Implemented now:** the access token is held **in memory only**. It is no
  longer written to `localStorage`, so it cannot be read by injected script or
  survive a tab close. This closes the specific XSS exposure the spec names.
* **Implemented now:** the refresh token remains in `localStorage` but is used
  solely to re-mint an access token. This is a deliberate, documented
  reduction in scope, not an oversight.
* **Not implemented:** httpOnly refresh cookie + CSRF tokens. This is a
  backend + deployment change (TLS, cookie domain, CSRF middleware, Android
  contract compatibility) that exceeds "repair the documented defect" and would
  change the API contract for a second client.

**Status:** FT-040 is **PARTIALLY VERIFIED**. The access-token half is
implemented and tested. The refresh-cookie half is recorded as **FT-065
(OPEN, HIGH)** in the ledger with this rationale, so it cannot be lost.

**Why not just do it:** implementing cookie auth without CSRF protection would
be a net *security regression* versus the current bearer-token model, and
implementing CSRF properly is a design change requiring product sign-off.

---

## RD-004 — FT-029: Forms, Reports and Settings pages

**Context:** Three pages render entirely hardcoded content with no API calls.

**Investigation:** Checked each against the planning documents.

| Page | Spec status | Backend support |
|---|---|---|
| Requirement Forms | Screen 23, feature H2; `requirement_forms` + `requirement_categories` tables exist | **No endpoints exist at all** |
| Reports | Screens 17–21, features K1–K6; `/reports/*` specified | **No endpoints exist at all** |
| Settings | Screen 24 | Partially — password change now exists (FT-023) |

**Decision:** The defect in FT-029 is that these pages **present fabricated data
as if it were real**, which is the actual harm. Building four report endpoints,
a requirement-form module and an export system is new feature development, not
repair, and is explicitly out of scope (repair rule: "Do NOT invent new product
functionality beyond the planning documents").

Therefore:
* Remove the fabricated content (fake form templates, invented "96.4%
  completion rate", fake geofence statistics).
* Replace with an honest, in-design "not yet available" state that names the
  capability.
* Make Settings show **real** configuration and the working password-change
  feature instead of a form that silently discards input.
* Record the unbuilt capabilities as deferred scope in the ledger.

**Status:** FT-029 repaired as a *misleading-data* defect. The absent modules
are recorded as **FT-066 (requirement forms)**, **FT-067 (reports)** and
**FT-068 (notifications)** — DEFERRED, with the spec references that define
them.

---

## RD-005 — FT-047: orphan media row

**Context:** `visit_media` contains one row whose `storage_key`
(`uploads/visits/.../site_photo_01.jpg`) has no corresponding file on disk.
The prior Phase 8 report called this "intentional".

**Investigation:** The key uses an `uploads/` prefix that the current
`FileValidationService.generate_storage_key()` never produces (it generates
`visits/{visit_id}/{media_id}_{name}`). The row was inserted directly by a seed
script, not through the upload pipeline, and no file was ever written.

**Decision:** This is a genuine data-integrity defect, not an intentional
fixture. A media record that cannot be downloaded is indistinguishable to the
UI from a real one until the user clicks it and gets a 404. Repaired by:
1. adding a maintenance command that detects orphans by comparing DB rows to
   storage, and
2. removing this specific row, with the reason recorded here (per repair
   rule 12).

**Status:** Implemented; verified by an integration test asserting that every
`visit_media` row resolves to a retrievable object.

---

## RD-006 — Android build environment

**Context:** FT-024 … FT-027 are Android contract and security defects.

**Blocker:** The module cannot be compiled in this environment:
* no Gradle wrapper (`gradlew`, `gradle/wrapper/gradle-wrapper.properties`),
* no JDK on PATH and `JAVA_HOME` unset,
* no Android SDK.

**Decision:** Repair what is deterministically verifiable by static analysis
(DTO field names against the live OpenAPI contract, insecure token storage), and
add the missing Gradle wrapper *files* where they can be authored correctly.
Do **not** claim a successful build. The exact blocker, the exact command, and
the exact error are recorded in `REPAIR_VERIFICATION.md`.

**Status:** Android items are **BLOCKED** for build/test verification and
marked as such — never VERIFIED.

---

## RD-007 — Visual identity untouched

Every frontend change in this program was behavioural. Colours, typography,
spacing, radii, component styling and the approved navy/amber League Spartan +
Libre Baskerville identity are unchanged. The design-source conflict recorded as
FT-030 (a stale UI Bible describing a different teal/Inter palette) remains a
documentation issue only; no code was changed for it.
