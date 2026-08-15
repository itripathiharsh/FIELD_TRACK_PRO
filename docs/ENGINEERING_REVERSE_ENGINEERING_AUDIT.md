# FieldTrack Pro — Engineering Reverse-Engineering Audit

**Audit type:** Read-only. No production code, schema, API, or UI was modified in the course of this review.
**Scope:** `fieldtrackpro-backend` (FastAPI/SQLAlchemy/Postgres+PostGIS), `fieldtrackpro-web` (React/TypeScript/Vite), `fieldtrackpro-android` (Kotlin/Jetpack Compose), plus `docs/` and repo-root documentation.
**Method:** Six independent read-only investigation passes (backend architecture/data-model, backend security, backend API/performance/reliability, web engineering, Android engineering, testing/observability/documentation), synthesized into this single document. Every finding below is traceable to a specific file and line; where a claim could not be independently verified, it is marked **UNVERIFIED** rather than assumed.
**Convention used throughout:** every finding is tagged **FACT** (neutral observation), **BUG** (will misbehave today), or **TECHNICAL DEBT** (works, but risky/messy/will not scale cleanly). Recommendations are separated from findings and explicitly marked **RECOMMENDATION**. Where a fix would change user-visible behavior, it is marked **PRODUCT DECISION — client confirmation recommended**; where it is a pure correctness/hardening fix with no behavior change, it is marked **ENGINEERING DECISION — no approval needed**.

---

## 1. Executive Summary

FieldTrack Pro is a three-tier field-sales visit-tracking system (FastAPI + Postgres/PostGIS backend, React admin/employee web app, Kotlin/Compose Android app) that has clearly been through multiple prior hardening passes — the codebase is full of comments referencing specific past defects (`FT-002`, `FT-025`, `FT-026`, `FT-046`, `FT-071`, etc.) and the fixes for those are visible and hold up under re-inspection. The architecture is layered correctly in the large (router → service → repository → DB), the data model is unusually thoughtful about historical-data integrity (immutable invoices, version-snapshotted form submissions, RESTRICT-vs-SET NULL cascade decisions with inline comments explaining *why*), and the backend integration test suite genuinely exercises a real Postgres database rather than mocking it away.

That said, this is not a system without real problems. Two backend endpoints (`GET /customers`, `GET /customers/{id}`) have **no employee/territory scoping at all**, meaning any authenticated field rep can read the entire outlet directory nationwide — a genuine IDOR-class vulnerability, and a startling one given that the *sibling* financial-data endpoint (`GET /customers/{id}/account`) is correctly scoped just a few files away. Payment recording has zero duplicate-submission protection, which matters because it is money. On Android, in-progress work (a form draft, an unsent photo) can be silently discarded on screen rotation or even ordinary recomposition, full-resolution photos are decoded into memory with no downsampling (a classic OOM path), a "Backend Server Configuration" screen ships in production allowing any user to redirect all API traffic (auth token included) to an arbitrary endpoint, and — most importantly given what this app exists to verify — check-in/check-out screens let a rep type in arbitrary GPS coordinates with nothing distinguishing that from a real sensor reading.

None of this requires a rewrite. The fixes are, almost without exception, small, targeted, and follow patterns the codebase already uses correctly somewhere else (the visit-scoping pattern that should apply to customers already exists for visits; the archive-guard pattern that should apply to territories already exists for form templates; the WorkManager retry infrastructure that should be wired up already exists, unused, in two files). The recommendation is **not** "no-go" — it is "fix five concrete, well-understood issues before this goes in front of real field reps handling real money and real outlet data," with a second tier of fixes that should follow shortly after. See §18 for the full prioritized list and §20/the final page for the shipping recommendation.

---

## 2. System Architecture

```
                     ┌─────────────────────────┐        ┌──────────────────────────┐
                     │   Web (React + TS)      │        │  Android (Kotlin+Compose)│
                     │  Admin console +        │        │  Field-rep app:          │
                     │  employee views         │        │  visits, GPS, forms,     │
                     │                         │        │  media, offline queue    │
                     └────────────┬────────────┘        └────────────┬─────────────┘
                                  │  HTTPS + JWT Bearer               │  HTTPS + JWT Bearer
                                  └───────────────┬────────────────────┘
                                                   ▼
                                    ┌───────────────────────────┐
                                    │   FastAPI app (app/api/v1)│
                                    │   17 routers, ~102 routes  │
                                    └─────────────┬─────────────┘
                                                   ▼
                                    ┌───────────────────────────┐
                                    │  Services (app/services)  │
                                    │  business rules, auth     │
                                    │  scoping, state machines   │
                                    └─────────────┬─────────────┘
                                          ┌────────┴────────┐
                                          ▼                 ▼
                              ┌───────────────────┐  ┌───────────────────┐
                              │ Repositories       │  │ Direct session.   │
                              │ (app/repositories) │  │ execute() (some   │
                              │ Visit/Payment/     │  │ services skip the │
                              │ Media/Customer/... │  │ repo layer)        │
                              └─────────┬───────────┘  └─────────┬─────────┘
                                        └──────────┬─────────────┘
                                                   ▼
                                    ┌───────────────────────────┐
                                    │  Postgres 17 + PostGIS 3.5 │
                                    │  Alembic-migrated, 12 revs  │
                                    └───────────────────────────┘
```

**Where business rules actually live** (traced per feature):

| Feature | Validation | Authorization | Persistence | Single-sourced? |
|---|---|---|---|---|
| Visit check-in/out + geofence | `GeoVerificationService` / `customer_service.verify_device_against_customer` | `visit_service.assert_visit_access` (canonical, reused everywhere) | `VisitRepository` | **Yes** — genuinely centralized |
| Aging / outstanding balance | `aging_service.compute_invoice_aging` (never stored, always derived) | `account_service.assert_employee_can_view_account` | `InvoiceRepository`/`PaymentRepository` | **Yes** |
| Visit state transitions | `visit_state_machine.assert_valid_transition`, used by both live check-in/out and the missed-visit scheduler job | same as above | — | **Yes** |
| Form-required-on-visit | `visit_service._validate_required_form` | `AdminOnly` on assignment; ownership check on submission | `Visit.required_form_id` | **Yes** |
| **Visit ownership ("does this employee own this visit?")** | — | **Three independent implementations** (see §6) | — | **No — duplicated** |
| **Required-questions-answered check** | Two independent copies inside the same file, one dead | — | — | **No — duplicated (one dead)** |
| **File-content validation** | `FileValidationService` (python-magic) for media/payments; `signature_service` reimplements its own narrower magic-byte check | — | — | **No — duplicated** |
| **Coordinate-bounds validation (Android)** | Implemented independently in 4 files | — | — | **No — duplicated on Android only** |

**Web ↔ Backend / Android ↔ Backend duplication**: both clients independently re-implement small pieces of backend-owned logic out of necessity (Android's `VisitDto.canCheckIn`/`canCheckOut` mirrors the backend's status-transition rule so the UI can gate a button without a round trip; Android's checkbox-answer JSON-array encoding is explicitly designed to match what the web client and backend expect). This is a **necessary, deliberate** duplication for offline-first UX, not an oversight — but nothing enforces it stays in sync beyond developer discipline (`FormTemplateModels.kt`'s own header comment says as much: "mirror `app/schemas/form_template.py` exactly... see `fieldtrackpro-web/src/types/index.ts` for the same contract"). This is flagged in §15 as a maintainability risk, not a bug.

---

## 3. Feature Inventory

| Feature | Status | Who sees it | Notes |
|---|---|---|---|
| Auth (login/refresh/logout/change-password) | Live, well-tested | Both roles | Bcrypt, JWT HS256, refresh-token rotation + hash storage |
| Employees / Territories / Customers CRUD | Live | Admin manages; both roles read | Customer read is **unscoped for employees — see §4** |
| Visit lifecycle (create, check-in, check-out, geofence verify) | Live, well-tested | Both (create/bulk = admin only) | Core product feature; correctly centralized authorization |
| Territory reassignment history | Live | Admin | Deliberate append-only history table, correctly RESTRICT'd |
| Form Template Builder (sections/questions/options/types/publish lifecycle/versioning) | Live | Admin builds; employee fills assigned forms | The system this session's prior work centered on; correctly versioned |
| Visit → Required Form assignment | Live (added this session) | Admin assigns; employee sees only their visit's form | Reviewed and tested in the prior session segment |
| Legacy "Requirement Form" (category/description/priority/timeline/budget/notes per visit) | **Dead** — 0 rows, no live UI trigger on any platform, but router/service/models/schemas still exist | Nobody reaches it | See §9 — candidate for removal, needs product confirmation |
| Visit Media (photo/file upload, checksum dedup) | Live | Both | Well-designed integrity checks |
| Digital Signatures | Live | Both | Same file-validation pattern as media, reimplemented separately (§6) |
| Order Capture (photographed order diary note) | Live | Both | Reuses media infrastructure correctly |
| Outlet Account (aging, outstanding, history) | Live | Admin full view; employee scoped to outlets they've visited | Correctly scoped, deliberately conservative trust model |
| Payment collection + verification workflow | Live | Employee submits; admin verifies/rejects | **No duplicate-submission protection — see §4/§10** |
| Invoice management | Live | Admin | Immutable-by-design, correctly unique-constrained |
| Excel/MIS bulk import (territories, customers, invoices, payments) | Live | Admin only | Best-designed reliability story in the codebase (see §11) |
| Reports (employee, customer history, productivity, geo-verification) | Live, Admin-only | Admin | No employee access path at all — clean boundary |
| Notifications | Live | Both, self-scoped | Simple, correctly scoped |
| Offline queue (check-in/out only) | Live | Employee (Android) | Does **not** cover forms/media/signatures — see §7 |
| Geofencing (Android background monitoring) | Live | Employee (Android) | Real leak/lifecycle bugs — see §7 |
| Backend Server Configuration override (Android) | Live, unconditionally shipped | Anyone with the app | Should not exist in a production build — see §4/§18 |

---

## 4. Security Audit

**Methodology**: every endpoint in every router under `app/api/v1/` was traced to its service function and, for any endpoint accepting a resource ID, the actual `WHERE`/filter logic was inspected to determine whether ownership is enforced server-side (not merely assumed from a frontend route guard).

### 4.1 Endpoint authorization matrix (condensed — full detail in the underlying audit trace)

| Router | Verdict | Basis |
|---|---|---|
| `auth.py` | SAFE | Rate-limited login, generic error on bad creds, self-only `/me` |
| `visits.py` | SAFE | `_resolve_employee_scope` forces server-side employee filtering on every read; `assert_visit_access`/`get_visit_for_user` gate every by-ID route |
| `media.py` | SAFE | Every route re-derives ownership via the visit; presigned local-file URLs are HMAC-signed (see caveat in 4.3) |
| `signatures.py` | SAFE | Same visit-ownership pattern as media |
| `payments.py` | SAFE (authorization) / **RISKY (financial integrity — see §10)** | `_assert_payment_visible` correctly blocks cross-employee access; but creation has no dedup |
| `invoices.py` | SAFE | Admin-only, no employee-facing by-ID route exists |
| `customers.py` | **VULNERABLE** | See 4.2 |
| `employees.py`, `territories.py`, `users.py` | SAFE | Admin-only CRUD; self-only `/me` and `/me/password` |
| `form_templates.py` (builder + submissions) | SAFE, with one **RISKY** exception | Submission ownership is correctly enforced everywhere; template list/detail leak DRAFT/ARCHIVED status to employees (4.4) |
| `requirement_forms.py` | SAFE (but see §9 — dead feature) | Inline-but-correct ownership check |
| `notifications.py` | SAFE | Server-forced `user_id` filter |
| `reports.py` | SAFE | Router-level `AdminOnly` dependency, no employee path exists at all |
| `geo.py` | **RISKY** | `/geo/verify-location` takes an arbitrary `customer_id` with no ownership scoping (4.2, secondary surface) |
| `imports.py` | SAFE | Router-level `AdminOnly` on all 7 routes |
| `health.py` | SAFE | Unauthenticated by design, no sensitive data returned |

### 4.2 VULNERABLE — Customer/outlet directory has no employee scoping

**Evidence**: `app/api/v1/customers.py:38-52` → `customer_service.get_customer`/`list_customers` (`app/services/customer_service.py:70-85`) → `CustomerRepository.list_by_territory` (`app/repositories/customer_repo.py:19-29`). None of these filter by the calling employee's territory or visit assignment; `GET /customers` only respects a client-*supplied* `territory_id`, and `GET /customers/{id}` is a bare fetch-by-id.

**Impact**: any authenticated EMPLOYEE — not just admins — can list or enumerate every outlet in the system: name, address, contact person, contact number, GPS coordinates, geofence radius, outlet code. This is the exact class of bug the codebase has already fixed once for visits (the `FT-002` comment trail) and deliberately fixed for financial data (`account_service.assert_employee_can_view_account`), but the fix was never extended to the base customer-profile endpoints. `/geo/verify-location` (`app/api/v1/geo.py:32`) has the same gap as a secondary surface — an employee can probe any outlet's geofence radius/proximity verdict without being assigned to it.

**Classification**: BUG / VULNERABLE. **Fix requires a product decision** (§18, P0-1) on the exact scoping rule (territory match? prior-visit assignment? both?) before implementation — this is not purely mechanical the way the P0 bugs below are.

### 4.3 RISKY — Presigned media URL signing reuses the JWT secret

`app/services/storage/local_provider.py:21-23` signs local-media download URLs with `settings.jwt_secret` — the same secret used for session authentication. Not independently exploitable today (the secret is never returned to a client), but it is a secret-separation weakness: rotating the JWT secret silently invalidates every outstanding download link and vice versa, and a future bug that leaks one secret compromises both trust boundaries at once.

### 4.4 RISKY — Form template list/detail leak non-published structure to employees

`GET /form-templates` and `GET /form-templates/{id}` (`app/api/v1/form_templates.py:129-155`) apply no status filter for non-admin callers, while the sibling `/render` endpoint explicitly enforces `PUBLISHED`-only for employees (`form_templates.py:281-287`). An employee can see draft/archived form names and question text through the plain list/detail routes even though the feature clearly intends employees to see published forms only.

### 4.5 RISKY — Login rate limiter is single-process only

`app/core/rate_limiter.py:17-19` self-documents that its 5-attempts/15-minute window is in-process state — it resets on restart and does not span multiple workers or replicas. In any horizontally-scaled deployment, this budget is bypassable simply by the load balancer routing retries to different workers. Whether this matters today depends entirely on deployment topology (**UNVERIFIED** — this audit did not inspect deployment configuration, since none exists — see §14).

### 4.6 RISKY — `/docs`, `/redoc`, `/openapi.json` always mounted; no security-header middleware

`app/main.py:33-35` mounts the full interactive API schema regardless of `environment`. No middleware sets `X-Content-Type-Options`, `X-Frame-Options`, HSTS, or a CSP anywhere in the codebase (confirmed by grep). Low effort, real defense-in-depth gap.

### 4.7 Audit trail — partial, not absent

There is **no general-purpose audit-log table** (confirmed: no `AuditLog`/`ActivityLog` model anywhere). What does exist, and is genuinely well-designed: `EmployeeTerritoryAssignment` records `created_by` for every reassignment (`app/models/employee_territory_assignment.py`); `Payment.reviewed_by`/`reviewed_at`/`rejection_reason` records who verified/rejected a collection; `FormTemplateVersion.published_by`/`published_at` records who published a given form version. **Absent**: any record of who edited a customer/employee profile, or who activated/deactivated a user account beyond the bare fact that it happened.

### 4.8 Android-side security findings

Covered in depth in §8, summarized here because they are genuinely security-relevant, not merely engineering debt:

- **"Backend Server Configuration" screen** (`ProfileSettingsScreen.kt:84-123`) ships unconditionally in production, letting any user redirect all API traffic — including the bearer token on every request — to an arbitrary endpoint. Combined with `android:usesCleartextTraffic="true"` applying app-wide (`AndroidManifest.xml:26`), this is a real credential/data-interception vector, not a theoretical one.
- **Manual GPS coordinate entry** on check-in/check-out (`CheckInScreen.kt:143-157`, `CheckOutScreen.kt:117-131`) lets a rep type in any latitude/longitude, and the surrounding code resets `accuracyM`/`isMock` to values indistinguishable from a genuine high-quality GPS fix (`CheckInViewModel.kt:64,90`). Since the app's entire reason for existing is verifying reps physically visited an outlet, this is the most business-critical security finding in the whole audit, not merely an Android polish issue.

### 4.9 What is genuinely correct and should not be second-guessed

Visit, media, signature, payment (read path), form-submission, notification, and reassignment-history authorization are all server-side enforced, correctly scoped, and covered by a real IDOR-focused integration-test file (`tests/integration/test_authorization_integration.py`). Password hashing (bcrypt), JWT handling (no hardcoded secret, fails closed if unset), refresh-token rotation with hash-only storage, and CORS configuration are all sound. The customer/geo findings above are real, but they are the exception in an otherwise disciplined authorization posture — not evidence of a systemic pattern.

---

## 5. Data Model Audit

**Overall verdict: structurally strong, with a handful of concrete gaps.** The team has clearly thought hard about historical-data integrity: `Invoice` is explicitly documented as immutable with derived-not-stored aging; `FormTemplateVersion` snapshots exist specifically so an admin editing a template can never retroactively alter a historical submission; `EmployeeTerritoryAssignment.territory_id` is deliberately `RESTRICT` (unlike the live `Employee.territory_id` pointer, which is `SET NULL`) so reassignment history can never silently lose its territory reference — with an inline comment explaining exactly why this asymmetry is intentional.

**Concrete gaps found:**

| # | Finding | Evidence | Class |
|---|---|---|---|
| 1 | `token_repo.py` compares a **naive** `datetime.utcnow()` against a tz-aware `expires_at` column — the only place in the codebase doing this; works today only because the DB server happens to run in UTC | `app/repositories/token_repo.py:21` | **BUG** (latent) |
| 2 | `Employee` and `Customer` have no `updated_at`, despite both being mutable via `PATCH` | `app/models/employee.py`, `app/models/customer.py` | TECHNICAL DEBT |
| 3 | `Territory.status` is a free-text `String(20)`, not an `Enum`, unlike every other status-like column (`VisitStatus`, `PaymentStatus`, `FormStatus`) | `app/models/territory.py:17` | TECHNICAL DEBT (consistency) |
| 4 | No index on `payments.status` or `visits.status` despite both being the primary filter for admin queue/list queries that run repeatedly (contrast: `form_templates.status` is indexed) | `app/models/payment.py:88`, `app/models/visit.py:27` | TECHNICAL DEBT (will matter at scale) |
| 5 | `FormSubmission` has no `UniqueConstraint` on `(form_id, visit_id, submitted_by)` despite the service layer relying on exactly that triple as an upsert key — makes the draft-save "upsert" a check-then-act race under concurrency | `app/models/form_template.py:148-164`, `app/services/form_template.py:634-666` | TECHNICAL DEBT |
| 6 | `Payment` has no unique/idempotency constraint of any kind — a double-submit creates two independent rows | `app/models/payment.py` | **BUG** (see §10, elevated to P0) |
| 7 | `territory_service.delete_territory` has no reference guard, unlike the equivalent `delete_template` — reproducible 500 if the territory was ever used in a reassignment-history row | `app/services/territory_service.py:63-66` | **BUG** (see §11) |

**Relationship correctness, entity by entity:**

- **Employee ↔ Territory**: `SET NULL` on the live pointer, `RESTRICT` on the history table — correct asymmetry, deliberately reasoned.
- **Visit ↔ Customer/Employee**: both `RESTRICT` — a customer or employee with visit history can never be deleted out from under that history. Correct.
- **Visit ↔ FormTemplate (required_form_id)**: `RESTRICT`, added this session, correctly reasoned and tested.
- **Visit ↔ VisitMedia/Signature/GeoLog**: `CASCADE` — these die with their visit, consistent with them not being independently historical/legal records the way payments are.
- **Visit ↔ Payment**: **no cascade, `RESTRICT`** — a visit with payments literally cannot be deleted. Correct, and consistent with `Payment` being financial history that must outlive the visit that generated it.
- **FormTemplate ↔ FormSubmission/FormAnswer**: `RESTRICT` at both levels (a form with submissions can't be deleted; an answered question can't be deleted) — enforced at both DB and service layer with friendly error codes. This is the correct, careful pattern that §5's other gaps (territory, payment) should be made to match.
- **FormTemplate ↔ RequirementCategory**: live and load-bearing — the "dead" `RequirementCategory` table is **not** fully orphaned; the current, live Form Template Builder's category dropdown depends on it. Anyone considering dropping this table must account for this dependency first (see §9).
- **Invoice/Payment**: immutable-by-design, aging always derived, never stored — correct and matches the payment-model's own documented distrust-by-default posture ("a payment... is never auto-trusted... this is deliberate, matching the client's explicit 'similar retailer name' mistrust concern").

**Migrations**: 12 revisions, single linear chain, no branch points, no multiple heads. Two transient model/migration mismatches were found (a `nullable=False` that was corrected two migrations later; a `Text` column later corrected to `JSONB`) — both were self-corrected in the very next revision with an inline comment explaining why, and neither represents a live defect today. Naming is consistent (`ix_`, `uq_`, `fk_` prefixes) across all 12 files.

---

## 6. API Audit

**Naming and HTTP-method conventions are consistently followed** — kebab-case multi-word resources, plural collection nouns, `PATCH` uniformly for partial updates, `POST` on a sub-path for state transitions (`/publish`, `/verify`, `/check-in`). No stray `PUT` anywhere in the codebase.

**Inconsistencies found:**

- **Error envelope `code` field has three different types depending on the failure path**: business errors (`BaseAPIException`) produce a string code; FastAPI's `RequestValidationError` handler produces an int (`422`); the generic crash handler in `app/exceptions/handlers.py` produces another int (`500`) but is **dead code** — `app/middleware.py`'s `CatchUnhandledExceptionsMiddleware` intercepts first and produces a *different* string code for the same case. A client-side error-code switch has to special-case all of this. TECHNICAL DEBT, low complexity to fix, no behavior change.
- **Ad-hoc, undeclared response shapes** on a handful of endpoints: `PATCH /notifications/{id}/read` returns a bare `{"status":"ok"}` instead of the updated resource (every other mutation returns the updated object); download-URL endpoints (`media`, `payments`, `signatures`) return an untyped dict with no `response_model`.
- **`GET /visits/{id}/requirement-form` returns `200` + `null` body when absent**, diverging from the rest of the API's "missing = 404" convention. Possibly intentional (absence is meaningful, not an error) — flagged as a genuine divergence either way.

**Pagination/filtering**: correctly bounded on `visits`, `customers`, `employees`, `payments/queue`, `imports`. **Unbounded and a REAL PROBLEM at the system's own stated scale**: `GET /form-submissions` has no `skip`/`limit` at all — an unfiltered admin call returns every submission ever recorded, each one then individually re-queried for context (see §10). **Unbounded and a POTENTIAL problem**: `/reports/geo-verification` has no forced date range and every check-in/check-out attempt (successful or failed) writes a row.

**Idempotency**: check-in has a real idempotency key; check-out and form-draft-save do not (see §10, §5 items 5-6). Excel import correctly dedups by natural key on both invoices and payments — re-committing the same file twice does not double-count revenue.

**Verdict: ACCEPTABLE, needs targeted refactor.** Not dangerous as a whole — the vast majority of the API is consistent and well-designed — but the payment-idempotency and form-submission-pagination gaps are real production risks that should be fixed before the volumes described in the product's own stated scale are reached.

---

## 7. Web Audit

**Routing**: every route is reachable from real navigation; no dead routes were found. One stale artifact — `Sidebar.tsx` still lists a `'MANAGER'` role in its `roles` arrays even though the backend removed that role (documented by the codebase's own `FT-038` comment) — harmless (the filter still matches correctly for the two real roles) but should be cleaned up.

**Confirmed bugs (will misbehave today):**

1. **`FormFillPage.tsx:78-83`** fires a full `POST /form-submissions` on every keystroke with no debounce and no in-flight sequencing. On a slow/mobile connection, out-of-order responses can let an older, less-complete answer snapshot become the persisted draft, silently discarding newer input.
2. **`ReportsPage.tsx:80-108`** re-fetches on every `dateRange` state change via a `useEffect` keyed on the `load` callback's identity, defeating the explicit "Apply Filter" button — picking a start date alone fires 3 parallel report requests before the user does anything else.
3. **`PaymentReviewPage.tsx:57-70`** creates a `Blob` object URL per proof photo viewed and never revokes it — unlike `MediaThumbnail.tsx`/`QuestionRenderer.tsx`, which correctly do. Every payment reviewed in an admin session permanently retains its photo in memory.
4. **`VisitDetailsPage.tsx:53-84`**'s data-loading effect has no `cancelled` guard (unlike `AuthContext.tsx`/`MediaThumbnail.tsx`, which do use one) — rapid navigation between two visits can let a slow response for the first visit overwrite state with stale data after the user has already moved to the second.

**Technical debt:**

- Duplicated report-row TypeScript interfaces between `client.ts` and `ReportsPage.tsx` — two sources of truth for the same backend shape, no compiler error if they drift.
- Duplicated `formatCurrency` helper (`AccountSummaryCard.tsx`, `PaymentReviewPage.tsx`).
- `GeoLogsPage.tsx` fetches all visits then fires one geo-log request *per visit* in parallel — will become a real performance cliff as visit volume grows (browsers queue past ~6 concurrent requests per host).
- Shared `Modal.tsx` has no focus trap or focus restoration — affects every modal in the app (a single fix here benefits the whole product).
- Form-builder's per-question numeric validation config (`min`/`max`, rating star count) is read correctly by the renderer but has **no authoring UI** — a dead capability, permanently unreachable through the web app as shipped.
- `FormFillPage`'s submit path never triggers a real `<form onSubmit>`, so HTML5 native constraint validation (`min`/`max`/`type=email`) never actually runs — required-ness is checked client-side, but format/range constraints are not. **The backend must be independently re-validating this** — this audit did not verify that it does, and it should be confirmed before relying on "the server catches it" as the safety net.
- Dead web-side `RequirementForm` API surface (`client.ts:776-799`, zero call sites) — the web counterpart of the confirmed-dead backend legacy feature. **Distinct and still-live**: `RequirementCategory`, which is actively used as the category picker for the (current, live) Form Template Builder — do not conflate the two when acting on this finding.

**Dependencies**: lean and non-duplicated (`lucide-react`, `maplibre-gl`, `react-router-dom`, no second HTTP client or date library, no state-management library beyond context). Nothing to remove here.

**Verdict**: solid engineering with a handful of concrete, fixable bugs concentrated in exactly the pages (forms, reports, payments) that matter most for correctness. Error/loading/empty states are consistently handled across every page sampled.

---

## 8. Android Audit

This is where the sharpest, highest-impact bugs in the whole system were found — concentrated in exactly the areas (state survival, GPS trust, media memory, upload reliability) that determine whether a field rep's actual workday goes smoothly.

**Confirmed bugs, ranked by real-world impact:**

1. **In-progress work is lost on rotation, and can be lost on ordinary recomposition.** `MainActivity` constructs every ViewModel as a plain Kotlin object in `onCreate` (no `configChanges`, no `ViewModelProvider`, no `SavedStateHandle`) — any rotation discards all of them. Worse: `NavGraph.kt:44-59` declares four ViewModels (`formFillViewModel`, `signatureViewModel`, `visitSummaryViewModel`, `collectionViewModel`) as **default-parameter expressions**, which Kotlin re-evaluates — creating a brand-new instance — on *any* recomposition of that call site, not just a config change. A form-fill-in-progress or a not-yet-uploaded signature can be silently discarded with no user action at all.
2. **Manual GPS coordinate entry with no gate** (see §4.8) — the single most business-critical finding in this audit.
3. **No accuracy or staleness threshold before trusting a location fix.** `LocationCaptureService.getCurrentLocation()` uses `getLastKnownLocation()`'s result immediately with no check on its age or accuracy — this call can return a fix that is minutes or hours old.
4. **Full-resolution photo decode with no downsampling**, on both the upload path (`MediaUploadScreen.kt:451-484`, reads the entire file into a `ByteArray`) and the preview path (`AttachmentPreviewScreen.kt:95-120`, `BitmapFactory.decodeByteArray` with no `inSampleSize`). A 12MP photo decodes to a ~48MB in-memory bitmap held alongside the raw byte array — the textbook Android OOM pattern, and this app's core workflow is photographing things.
5. **Documented, built retry infrastructure that is never used.** `MediaUploadWorker.kt`/`SignatureUploadWorker.kt` implement exactly the backoff-retry behavior a field app needs for spotty connectivity — and are never enqueued anywhere in the app. A failed upload on a bad connection is simply lost unless the rep notices the error banner and manually retries.
6. **Geofence registration is never torn down.** No `DisposableEffect` stops monitoring when `VisitDetailsScreen` leaves composition, and `startMonitoring()` never removes the previous geofence before registering a new one — visiting N outlets in a shift registers N geofences that accumulate toward the OS's ~100-per-app ceiling and keep consuming background location callbacks for outlets the rep already left.
7. **Check-out has no idempotency key**, unlike check-in — mitigated in the common case by a pre-flight status check, but not race-safe under concurrent retries.
8. **Offline-queued check-in/out retries fabricate GPS metadata.** The queued action stores only lat/lng/timestamp — not the original accuracy or mock-location flag — so a retry after reconnecting reports fabricated "good GPS" defaults regardless of what the original offline attempt actually measured.
9. **Two Composables bypass the ViewModel/Repository layering entirely** (`VisitDetailsScreen.kt`, `AttachmentPreviewScreen.kt`), instantiating a repository directly inside `LaunchedEffect` — inconsistent with every other screen and untestable the way the rest of the app is.
10. **"Backend Server Configuration" ships in production** (see §4.8).

**Confirmed dead code (unchanged from a prior audit this session, re-verified):** `Screen.RequirementForm`/`RequirementFormScreen`/`RequirementViewModel`/`RequirementRepository`/`RequirementApi` are still fully wired into the `NavHost` but have zero navigation call sites anywhere. `FormTemplateRepository.listPublishedForms()` is now dead code left over from the earlier fix of the global-form-list bug.

**Testing**: all 18 test files are JVM unit tests; `app/src/androidTest/` is empty — zero Compose UI/instrumented tests exist. Two tests (`CheckInGatingTest`, `ConflictDetectionTest`) re-implement a private copy of the production logic they're meant to protect and test that copy instead — they provide **zero regression protection** for the actual code. By contrast, the DTO contract tests (`DtoContractTest`, `FormTemplateDtoTest`, etc.) and `VisitStateTransitionTest` are genuine, valuable coverage that would have caught (and historically did catch, per the codebase's own `FT-025`/`FT-026` comments) real field-name mismatches.

**Verdict**: the security-sensitive design intent is right (comments explicitly state "the server is the security boundary, not the client geofence trigger" — a correct and mature framing), but several of the concrete implementations undermine that intent (manual coordinate entry, no accuracy gate) or simply have not been finished (the unused upload-retry workers). Several of these findings — state loss, OOM, geofence ceiling — are exactly the class of bug that is easy to miss in an emulator and only surfaces on a real device under real field conditions; **this audit could not verify them on a physical device and explicitly flags that as required before sign-off** (see §20).

---

## 9. Feature Removal / Simplification Candidates

| Candidate | What it does | Why it looks unnecessary | Depends on it | Safe to remove now? | Confirmation needed? |
|---|---|---|---|---|---|
| Legacy "Requirement Form" (backend router+service+models, web dead client methods, Android dead screen/viewmodel/repo) | Per-visit free-text category/description/priority/timeline/budget/notes submission | Zero rows in the database, zero live navigation trigger on web or Android, fully superseded by the FormTemplate + `Visit.required_form_id` system built this session | Nothing live — `RequirementCategory` (the table, not the form-submission workflow) is still used by the *current* Form Template Builder's category picker and must **not** be swept into this removal | **No** — the routes/screens/methods are dead and could be deleted mechanically, but this is a whole product-facing feature concept being retired, not a refactor. **Requires product/client confirmation** that this per-visit workflow is genuinely superseded, not paused. |
| `territory_service.is_location_within_territory` | Superseded Haversine-based distance check | Zero callers anywhere in the codebase; the live geofence check uses PostGIS instead, for good reason (this Haversine approach is the same imprecise method a past bug, `FT-004`, was traced to) | Nothing | **Yes** | No — this is dead utility code, not a feature. Engineering decision. |
| `FormTemplateRepository.listPublishedForms()` (Android) | The global-fetch method the earlier session's bug fix replaced | No longer called anywhere | Nothing | **Yes** | No — dead code left over from a completed fix. Engineering decision. |
| "Backend Server Configuration" screen (Android) | Lets a user override the API base URL at runtime | No end-user business value in a production build; pure dev/QA convenience | Nothing production-relevant | **Yes, for the production build specifically** (gate behind `BuildConfig.DEBUG` rather than deleting the capability outright, since it likely remains useful for QA/dev builds) | No — this is a security hardening fix, not a product decision. |
| Manual lat/lon entry on check-in/check-out (Android) | Lets a rep bypass GPS entirely by typing coordinates | Undermines the app's core anti-fraud guarantee with no visible gate | **UNVERIFIED** whether any legitimate "GPS unavailable" business workflow depends on this today | **No** — do not remove unilaterally. **Requires product decision** on whether a GPS-unavailable fallback is genuinely needed, and if so, what review/flagging should wrap it. |

No other feature inspected across web, Android, or backend was found to be dead, redundant, or without live business use. Nothing in this audit recommends removing a *working* feature that field reps or admins actually rely on — the removal candidates above are either already-inert code paths or an admin-only debug convenience that was never gated out of production.

---

## 10. Performance Audit

| Finding | Evidence | Classification |
|---|---|---|
| `GET /form-submissions` unbounded (no pagination) + N+1 context resolution per row (self-acknowledged in the code's own docstring) | `app/api/v1/form_templates.py:532-557,320-362` | **REAL PROBLEM** — this is the one list endpoint whose growth trajectory genuinely matches the system's own stated scale ("thousands of submissions") |
| `POST /payments` has no duplicate-submission protection | `app/services/payment_service.py:71-111` | **REAL PROBLEM**, financial (also a reliability finding, §11) |
| `list_templates` — 3 separate COUNT queries executed per template in a loop | `app/api/v1/form_templates.py:136-148` | POTENTIAL PROBLEM (bounded by template count today — dozens) |
| `bulk_create_visits` — one SELECT per customer_id in the batch instead of one `IN (...)` query | `app/services/visit_service.py:392-403` | POTENTIAL PROBLEM (real if bulk operations regularly cover >20-30 outlets) |
| Excel import commit — per-row flush for newly-created territories/customers | `app/services/import_service.py:746-776` | POTENTIAL PROBLEM (one-time admin operation, not end-user-facing) |
| No index on `payments.status`/`visits.status`, both filtered repeatedly by admin queue/list views | `app/models/payment.py:88`, `app/models/visit.py:27` | POTENTIAL PROBLEM today, **will become REAL** once row counts grow past a few thousand |
| PDF/CSV generation runs synchronously in the request | `app/services/pdf_service.py`, `app/api/v1/imports.py:113-126` | **NOT A PROBLEM** at this scale — both are small, bounded documents completing in well under 100ms |
| `GeoLogsPage.tsx` (web) fetches every visit then fires one geo-log request per visit | `GeoLogsPage.tsx:25-34` | POTENTIAL PROBLEM — will become real as visit volume grows |
| Android: full-resolution image decode with no downsampling | `MediaUploadScreen.kt`, `AttachmentPreviewScreen.kt` | **REAL PROBLEM** on real devices — see §8 |
| Android: unbounded, unencrypted offline queue with O(n) read/write per operation | `OfflineQueueManager.kt` | POTENTIAL PROBLEM — only manifests after extended offline periods |

**Not flagged as problems** (explicitly checked, found fine): templates/territories list endpoints (dozens of rows, admin-curated), notifications (naturally bounded per-user), customer account/order history (naturally bounded per outlet), web bundle dependencies (lean, no duplication found), report-data aggregation queries (single grouped SQL statements, not Python-side aggregation).

---

## 11. Reliability Audit

Traced against the specific failure scenarios the audit was asked to consider:

| Scenario | What actually happens (traced in code) | Verdict |
|---|---|---|
| Excel import interrupted partway | `commit_import_batch` wraps all four write passes in one try/except; any exception triggers rollback and marks the batch `FAILED` with a reason — no half-committed rows | **Handled correctly** |
| Invoice/payment imported twice (via import pipeline) | Both dedup by natural key (`customer_id`+`invoice_number`; `customer_key`+`source_reference`) | **Handled correctly** |
| Payment recorded twice (via manual UI, double-tap) | No idempotency key, no unique constraint, no natural-key dedup — creates two independent rows | **BUG — the sharpest reliability gap in the system** |
| Invoice created twice concurrently (race, not sequential) | DB unique constraint protects data integrity, but the uncaught `IntegrityError` falls through to a raw 500 instead of the intended clean `409` | POTENTIAL PROBLEM (low likelihood, ugly failure mode) |
| Form submitted twice rapidly (double-click submit) | Status check prevents a duplicate *finalized* record — worst case is an overwritten `submitted_at`, no duplicate business record | **Not a problem** |
| Form draft saved twice rapidly (double-click / retry) | Upsert-by-triple has no DB constraint backing it — a genuine race can create two DRAFT rows for the same form+visit+employee | TECHNICAL DEBT (real but low-severity — drafts, not final submissions) |
| Media/signature/payment-proof upload: storage succeeds, DB write fails | Rollback + best-effort delete of the orphaned storage object, with a warning logged if that delete also fails | **Handled reasonably**; a residual disk-space leak (not a data-integrity risk) exists if the process crashes between the two steps |
| Admin archives a form template referenced by an in-progress visit | `delete_template` has an explicit reference guard; **`archive_template` does not** — an in-progress visit's `required_form_id` can point at a now-archived template that the assigned employee can no longer be served (`render_form` blocks non-admins from archived forms), with no automatic remediation | TECHNICAL DEBT — real edge case, needs admin awareness or an automated fix |
| Admin deletes a territory currently referenced by reassignment history | No guard at all — reproducible: create territory → assign an employee via the reassignment feature → delete the territory → uncaught `IntegrityError` → raw 500 | **BUG** (elevated to P0, §18) |
| Employee changes territory while a visit is active | A dedicated test confirms reassignment does not retroactively alter an already-recorded visit's customer/territory; no test covers reassignment during a visit that is literally checked-in-but-not-checked-out | POTENTIAL GAP (not confirmed broken, just untested) |
| App killed during Android sync | Offline queue persists to `SharedPreferences` (survives process death); in-flight (non-queued) form/media/signature uploads have no equivalent persistence — see §8 | Mixed: check-in/out safe, everything else is not |

---

## 12. Testing Audit

**Backend**: the integration suite (`tests/integration/`, 27 files) is genuinely real — it seeds rows via direct SQL into a real Postgres database, authenticates via a real `/auth/login` call, and asserts against an independent database connection rather than mocking anything. Grep for mocking frameworks across `tests/integration/` returns zero hits. This is a strong foundation. Confirmed **covered**: IDOR protection across visits/media/payments/geo-logs, form-version-snapshot correctness (a genuinely strong test that publishes v1, submits, edits to v2, and confirms the old submission still shows v1's structure), duplicate-invoice rejection, double-review rejection, malformed/duplicate Excel rows, geofence-outside-radius rejection (unit-level only, not confirmed at the integration/HTTP layer), and archived-form-cannot-be-assigned. Confirmed **gap**: the `ALREADY_SUBMITTED` 409 path (real production code) has zero test exercising it; mid-visit territory reassignment is untested; a couple of tests use a weak `status_code in (200, 404)` assertion that accepts either outcome and proves only "didn't crash."

**Android**: 18 unit test files, zero instrumented/Compose UI tests (`app/src/androidTest/` is empty). The DTO contract tests and `VisitStateTransitionTest` are genuinely valuable. Two tests (`CheckInGatingTest`, `ConflictDetectionTest`) test a hand-copied duplicate of private production logic rather than the logic itself — they cannot catch a real regression. Several trivial "constructor echo" tests (e.g. `SignatureDtoTest`, `NotificationDtoTest`) assert nothing beyond "the fields I passed in come back out."

**Web**: error/loading/empty-state coverage is consistent across the pages sampled in §7. `TerritoryDetailPage.test.tsx` has been characterized in earlier work this session as a "pre-existing flaky test" — this audit ran it three times and found the failure is **100% deterministic, not flaky at all**: `TerritoryDetailPage.tsx` renders the territory name in two separate DOM nodes at once (`PageHeader.tsx:31-33`'s `<h1>` and `TerritoryDetailPage.tsx:421-423`'s own `<h2>`), so `screen.findByText('North Region')` matches two elements and throws "Found multiple elements" on every poll; because `findByText` retries via `waitFor` for its ~1000ms default timeout before re-throwing, the failure *looks* like a timing race (each failing test takes ~1000ms) when it is actually a deterministic assertion bug. Two more assertions in the same test (`/Field Representatives: 1/`, `/Customer Accounts: 1/`) would never pass even if the ambiguity were fixed, since the component renders the label and count as separate DOM nodes, not one combined string. **This should be re-labeled from "known flaky test, ignore" to "known real bug, fix the test (and consider whether the page needs two identical headings at all)."**

`FieldTrackMap.test.tsx` contains 7 tests; **6 of the 7 assert nothing but `expect(true).toBe(true)`** (lines 75, 80, 85, 90, 99, 108) despite test names claiming to cover marker rendering, clustering, and invalid-coordinate filtering — these provide zero actual regression protection for the behavior they claim to test. The 7th only checks that *some* `<div>` exists.

Confirmed test-coverage gaps: no test exercises geofence check-in/check-out **rejection** (`VisitDetailsPage.tsx`'s `submitGeoAction` error path is entirely untested — the 5 existing `VisitDetailsPage.test.tsx` tests only cover admin-status-override RBAC); no test sets an archived form template and asserts on the resulting UI (editing blocked, archived badge, filtered from active list) despite the fixtures already carrying the necessary `archived_at`/`version` fields; and no test asserts client-side behavior when an employee opens a resource that isn't theirs (nav-visibility RBAC is tested, but not an ownership-denied page render).

Web has **no crash-reporting/error-telemetry SDK** (confirmed: no Sentry/LogRocket/Bugsnag/Rollbar/Datadog in `package.json`). A global `ErrorBoundary` (`src/components/ui/ErrorBoundary.tsx`) is correctly wired at the app root and will catch any uncaught render error, but it only does `console.error` — the failure is never reported anywhere beyond the local browser console.

**Recommended test additions** (protecting real business behavior, not chasing a coverage number):
- One integration test exercising `ALREADY_SUBMITTED` on a double-submit.
- One integration test for territory deletion while referenced by reassignment history (would catch the P0 finding in §11 immediately).
- One integration test for payment double-submission (would catch the P0 finding in §10 immediately and prevent regression once fixed).
- One Android instrumented test (or at minimum, extract the check-in-gating and conflict-detection logic into a *public*, directly-testable function) so those two tests actually protect the code they claim to.

---

## 13. Observability Audit

**Logging**: thin. Only 9 `logger.info` and 5 `logger.error` call sites across 15 files that import `logging` on the backend; Android has `Log.*` calls in only 3 files, and every repository/ViewModel/worker elsewhere is silent. Several exception handlers swallow failures with a genuinely empty catch block and no log line at all (`app/api/v1/health.py`'s DB-check failure path logs nothing; `OfflineQueueManager`'s JSON-parse failure silently becomes "empty queue" with no log — meaning a corrupted offline queue on Android would lose pending check-ins with zero trace).

**Crash reporting**: absent on both Android (no Crashlytics/Sentry/Bugsnag — confirmed via dependency grep) and web (no Sentry/LogRocket/Bugsnag/Rollbar/Datadog — confirmed via `package.json` grep). Web's `ErrorBoundary` catches uncaught render errors app-wide but only logs to the browser console, never reports anywhere.

**Correlation/tracing**: no request-ID or correlation-ID middleware exists anywhere in the backend — a production incident spanning multiple log lines for one request cannot be automatically correlated.

**Health check**: `/health` is a static 200 with no DB check; `/health/db` genuinely queries the database (`SELECT 1`) and returns 503 on failure — this one is real, not decorative, but its failure branch is itself unlogged (see above).

**Audit trail for diagnosis**: territory reassignment and payment review both have a real, queryable history (see §4.7) — an engineer investigating "who changed this and when" for those two areas has an actual answer. For customer/employee profile edits or user activation toggles, there is no equivalent answer today.

---

## 14. Documentation Audit

| Document | Verdict | Evidence |
|---|---|---|
| Backend README | GOOD (build/run/test), **MISSING** (env vars not enumerated — `JWT_SECRET`, `CORS_ALLOWED_ORIGINS`, storage/Firebase vars all absent from the instructions despite existing in `.env.example`) | `fieldtrackpro-backend/README.md` |
| Top-level README | GOOD content, doc-hygiene smell — backend and frontend run instructions are each duplicated verbatim in two separate sections, suggesting an append rather than an edit | repo-root `README.md` |
| Android README | MISLEADING — points at `.env.example` variables (`BASE_URL`, `GOOGLE_MAPS_API_KEY`) the app never actually reads, while omitting `MAPLIBRE_TILE_URL`, the one build property that genuinely matters. **MISSING**: release-signing instructions (and no keystore/signing config exists in the repo at all — a release build today would ship unsigned/debug-defaulted) | `fieldtrackpro-android/README.md`, `app/build.gradle.kts` |
| Web README | GOOD (dev server, build), **MISSING** (never mentions `npm test`/`npm run test:coverage` despite both being defined in `package.json` and 21 test files existing), **OUTDATED/MISLEADING** (documents only 2 of 3 real env vars — omits `VITE_MAPLIBRE_TILE_URL`; states the `VITE_API_BASE_URL` default as `http://localhost:8000/api/v1`, but the code's actual fallback in `src/config/env.ts:6` is `http://127.0.0.1:8000`, a different value) | `fieldtrackpro-web/README.md`, `.env.example`, `src/config/env.ts` |
| `docs/MASTER_REVERSE_ENGINEERING_CHECKLIST.md` | **MISLEADING** — marks the Requirement-Form feature as entirely absent (`Exists: NO` throughout), directly contradicted by the live, shipped router/service/models this same audit confirmed exist | Contradicted by `app/api/v1/requirement_forms.py` and its full service/schema/model stack |
| `docs/final_forensic_audit/11_FINAL_VERDICT.md` | **OUTDATED** — claims "43 routes," current count is ~102; form-templates/invoices/payments/imports (dozens of routes) are not mentioned at all | Route count verified by counting `@router.*` decorators today |
| `docs/phase_06_maps_geospatial/05_COMPLETION_REPORT.md` | **OUTDATED** — frames Google Maps SDK as the pending blocker; the shipped app uses MapLibre exclusively on both web and Android | `build.gradle.kts` dependencies, `MapScreen.kt` imports |
| `docs/forensic_audits/maps_visibility/03_FINDINGS.md` | Accurately historical, but dangerous read in isolation — correctly superseded by a later repair report, but nothing in the findings doc itself signals that | Cross-checked against `docs/repairs/maps_visibility/04_COMPLETION_REPORT.md` |
| Form-versioning business rule | **MISSING as a doc** — exists only as an inline code comment on `FormTemplateVersion`, despite being one of the most important guarantees in the system | `app/models/form_template.py` |
| Payment-trust workflow (`PENDING_VERIFICATION` → admin review → counts toward outstanding) | **MISSING as a doc** — exists only as an inline model docstring | `app/models/payment.py` |
| Deployment/CI/CD | **MISSING entirely** — no Dockerfile, no docker-compose, no CI workflow, no runbook anywhere in the repository | Confirmed via exhaustive search |

Stray dev-run log files (`server_debug.log`, `server_error.log`, `server_log.txt`, `server_trace.log`) sit in the backend repo root — harmless but should be gitignored.

---

## 15. Engineering Smells

Distilled list of "if I inherited this tomorrow, this is what I'd flag in week one":

- **Business rule duplicated in 3 places when 1 already exists as the canonical, tested version** — visit-ownership checking (`visit_service` vs. two independent copies in routers). This is the exact class of problem the codebase's own commit history shows it already fixed once for a different rule.
- **Two competing backend patterns for the same job** (repository-layer vs. inline `session.execute` in the service) with no obvious rule for which aggregate gets which — a newcomer cannot predict this from the model name alone.
- **A guard pattern exists for one entity (form templates) but was never copied to a structurally identical entity (territories)** — this is the single most reproducible bug found in this audit (§11) and the fix is "copy the pattern that already works."
- **Built, working retry infrastructure sitting completely unused** on Android (`MediaUploadWorker`/`SignatureUploadWorker`) — the hardest part (backoff logic) is already done; wiring it in is the missing 20%.
- **A debug convenience shipped unconditionally into production** (Android's API base-URL override) — the kind of thing that's obviously fine in a dev build and obviously wrong in a release build, and just needs a build-type gate.
- **Docs that actively contradict the current codebase** rather than simply being silent about it — worse than no documentation, because they actively mislead a reader who trusts them (§14).

---

## 16. What Is Already Good

Worth stating plainly, since an audit's job is not to manufacture problems:

- The **visit/media/signature/payment/form-submission authorization model** is correctly centralized, consistently applied, and backed by a real IDOR-focused test suite. This is the pattern every other part of the system should be measured against.
- The **data model's historical-integrity design** (immutable invoices, version-snapshotted submissions, deliberate RESTRICT-vs-SET NULL cascade choices with inline rationale) reflects real engineering thought about what must never silently change.
- The **Excel import pipeline** is the single best-designed subsystem in the codebase from a reliability standpoint: atomic commit-or-rollback, natural-key dedup on both invoices and payments, clean error reporting per row.
- The **backend integration test suite** genuinely tests against a real database with real authentication — this is not a suite that will give false confidence.
- **Android's DTO contract tests** have a proven track record (the codebase's own comments cite two real historical bugs they would have caught) and should be extended, not replaced.
- The **web design system's component reuse** (`StatusBadge`, `EmptyState`, `ErrorBanner`, `DataTable`, `AccountSummaryCard`) is genuinely shared and consistently applied — this is not duplicated UI pretending to be reusable.
- The **geofencing security framing** ("the server is the security boundary, the client trigger is a convenience") is the *correct* architectural stance, even though two Android implementation details (§8) currently undermine it in practice.

---

## 17. What Should NOT Be Changed

- The visit/media/payment/form ownership-check pattern in `visit_service.py` — this is the thing to *copy*, not touch.
- Form versioning / `FormTemplateVersion` snapshot design — correct, tested, exactly matches the stated business need.
- Excel import's transactional + dedup design — already resilient to every "imported twice" scenario this audit was asked to check.
- Payment/Invoice immutability and derived-not-stored aging — deliberate and correct.
- The web shared-component library — don't refactor working, correctly-reused UI.
- Android's DTO contract-test suite and `VisitStateTransitionTest` — extend, don't replace.
- The already-completed conclusion (from earlier work this session) that the legacy RequirementForm backend system is dead code with zero live rows — do not re-litigate; act on it per §9's confirmation requirement instead.
- The `Visit.required_form_id` design and its `lazy="joined"` relationship strategy added earlier this session — already reviewed and tested; leave as-is.

---

## 18. P0 / P1 / P2 / P3 Recommendations

### P0 — MUST FIX BEFORE PRODUCTION

**P0-1. Customer/outlet directory has no employee scoping (IDOR).**
Evidence: `app/api/v1/customers.py:38-52`, `app/services/customer_service.py:70-85`, `app/repositories/customer_repo.py:19-29`, `app/api/v1/geo.py:32`. Why it matters: any employee can read every outlet's PII and GPS coordinates nationwide. Risk: data-privacy violation, competitive-intel leak, and it compounds the GPS-spoofing risk below. Fix: apply the same server-side scoping pattern already used for visits. Complexity: LOW-MEDIUM. Changes business behavior: **YES — PRODUCT DECISION required** on the exact scoping rule before implementation.

**P0-2. Payment creation has zero duplicate-submission protection.**
Evidence: `app/services/payment_service.py:71-111`, no `UniqueConstraint` on `Payment`, no idempotency key on `PaymentCreate`. Why it matters: it's money — a double-tap creates two independent unverified collection records. Fix: add a client-generated idempotency key + constraint, or a natural-key dedup window. Complexity: LOW-MEDIUM. Changes business behavior: minimal (adds a rejection path for exact duplicates). **ENGINEERING DECISION — no approval needed.**

**P0-3. Android ships a production API base-URL override + unconditional cleartext traffic.**
Evidence: `ProfileSettingsScreen.kt:84-123`, `AndroidManifest.xml:26`. Why it matters: full traffic (incl. bearer token) can be redirected by anyone with the app. Fix: gate the override screen behind `BuildConfig.DEBUG`; remove app-wide cleartext. Complexity: LOW. **ENGINEERING DECISION — no approval needed.**

**P0-4. Manual GPS coordinate entry on check-in/check-out with no gate or distinguishing signal.**
Evidence: `CheckInScreen.kt:143-157`, `CheckOutScreen.kt:117-131`, `CheckInViewModel.kt:64,90`. Why it matters: this defeats the app's core anti-fraud guarantee — verifying a rep physically visited the outlet — and is worsened by P0-1 handing every employee the exact coordinates to type in. Fix: remove from the production flow, or replace with an explicit, flagged "GPS unavailable" exception path. Complexity: MEDIUM. **PRODUCT DECISION required** on the fallback UX.

**P0-5. Territory deletion is unguarded — reproducible crash or silent data loss.**
Evidence: `app/services/territory_service.py:63-66`. Why it matters: a plausible, reproducible admin action (delete a territory that was ever used in a reassignment) throws an uncaught 500; the non-crashing path silently nulls territory references on employees/customers with no warning. Fix: copy the reference-guard pattern already used in `delete_template`. Complexity: LOW. **ENGINEERING DECISION — no approval needed.**

### P1 — SHOULD FIX SOON

1. Form-template list/detail leak DRAFT/ARCHIVED structure to employees — apply the same status filter `/render` already uses. LOW complexity, no approval needed.
2. Presigned media URL signing reuses the JWT secret — derive a separate signing key. LOW-MEDIUM complexity, no approval needed.
3. Login rate limiter is single-process only — move to shared storage if/when deployed with multiple workers. MEDIUM complexity, depends on deployment topology (confirm with infra first).
4. `/docs`/`/redoc`/`/openapi.json` always mounted; no security-header middleware. LOW complexity, no approval needed.
5. `token_repo.py`'s naive-datetime comparison against a tz-aware column. LOW complexity, trivial fix, no approval needed.
6. Android's built retry infrastructure (`MediaUploadWorker`/`SignatureUploadWorker`) is never wired up — real uploads have no retry on failure. MEDIUM complexity, high field-reliability value, no approval needed.
7. Android state loss on rotation/recomposition (`MainActivity`'s plain-object ViewModels; `NavGraph`'s default-parameter ViewModels). MEDIUM complexity, no behavior change, **needs real-device verification**.
8. Android geofence never unregistered on screen exit/visit switch. LOW-MEDIUM complexity, no approval needed, **needs real-device verification**.
9. Android: no accuracy/staleness gate before trusting a GPS fix. MEDIUM complexity, minor behavior change (occasional wait for a fresh fix) — light product confirmation on thresholds recommended.
10. Android: full-resolution photo decode/upload with no downsampling — real OOM risk. MEDIUM complexity, no behavior change, **needs real-device verification**.
11. Web `PaymentReviewPage.tsx` blob-URL leak. LOW complexity, no approval needed.
12. Web `FormFillPage.tsx` per-keystroke autosave race — add debounce/sequencing. LOW-MEDIUM complexity, no approval needed.
13. Web `ReportsPage.tsx`'s auto-refetch defeats its own "Apply Filter" button. LOW complexity, no approval needed.
14. `ALREADY_SUBMITTED` 409 path has zero test coverage. LOW complexity, testing-only.
14b. `TerritoryDetailPage.test.tsx`'s 3 "flaky" failures are actually a deterministic bug: `PageHeader`'s `<h1>` and the page's own `<h2>` both render the territory name, so `findByText` matches two elements and fails every time (mistaken for flakiness because the retry-timeout makes it *look* like a race). Fix the test to use a more specific query (or add a `data-testid` to disambiguate), and separately decide whether the page needs two identical headings at all. LOW complexity, no approval needed.
14c. `FieldTrackMap.test.tsx` — 6 of 7 tests assert `expect(true).toBe(true)` and provide zero actual coverage of the marker/clustering/invalid-coordinate behavior their names claim to test. Rewrite with real assertions on rendered marker count/DOM state. LOW-MEDIUM complexity, testing-only.
15. `GET /form-submissions` unbounded + N+1 context resolution — add pagination and batch the context lookup the same way `form_id`/`form_name` is already batched two lines above it. MEDIUM complexity, no approval needed.

### P2 — ENGINEERING IMPROVEMENT

Consolidate the 3x duplicated visit-ownership check into the canonical helper; consolidate the 2x duplicated required-answers check (one copy is dead); consolidate `signature_service`'s hand-rolled file-magic check into the shared `FileValidationService`; delete `territory_service.is_location_within_territory` (dead code); add missing indexes on `payments.status`/`visits.status`; add `updated_at` to `Employee`/`Customer`; convert `Territory.status` to a real enum; add a DB constraint backing the form-draft upsert; add a reference guard to `archive_template` (mirroring `delete_template`); batch `bulk_create_visits`' per-customer query loop; batch the import pipeline's per-row invoice-update lookup; fix the error-envelope `code`-type inconsistency; standardize the remaining ad-hoc response shapes; add focus-trap/restore to the shared web `Modal`; extract the duplicated `formatCurrency` util; delete the duplicated report-row TypeScript interfaces; consolidate Android's 4x duplicated coordinate-bounds validation; clean up the stale `'MANAGER'` role residue on web and Android; add basic structured logging/correlation on the backend; add Android crash reporting; gitignore the stray backend log files; correct the outdated/misleading docs identified in §14; write short design-decision docs for form-versioning and the payment-trust workflow (currently code-comment-only); fix the top-level README's duplicated sections.

### P3 — OPTIONAL / FUTURE

Verify whether `maplibre-gl` is actually code-split away from employee sessions that never open a map; the hand-rolled PDF exporter's non-ASCII character risk (real only if report data ever contains non-Latin-script names — not observed in current data); add Compose UI/instrumented tests for Android (nice-to-have, current unit-test discipline is already reasonable); consider whether an OpenAPI-codegen step for shared web/Android types would reduce the "mirror the schema by hand" drift risk long-term — a genuine idea, but HIGH complexity/churn risk for a feature-complete system, so future-only; harden `LocalStorageProvider`'s path-traversal guard for defense-in-depth (not currently exploitable).

### DO NOT TOUCH — WORKING / LOW VALUE TO CHANGE

Everything listed in §17.

---

## 19. Overall Engineering Scorecard

| Dimension | Score | Rationale |
|---|---|---|
| Architecture | 78/100 | Correctly layered in the large; two coexisting backend patterns (repo vs. inline query) without a clear rule for which aggregate gets which |
| Security | 62/100 | Core visit/media/payment authorization is excellent and tested; but a real, unscoped-directory IDOR and Android's GPS-trust gaps are genuine, not theoretical |
| Data model | 85/100 | Unusually thoughtful historical-integrity design; a handful of concrete gaps (missing constraints/indexes, one naive-datetime bug) |
| API design | 74/100 | Consistent naming/methods; real pagination and idempotency gaps at exactly the two places (submissions, payments) that matter most |
| Web engineering | 72/100 | Lean, well-reused component library; four confirmed real bugs concentrated in forms/reports/payments |
| Android engineering | 58/100 | Correct security *framing*, undermined by concrete implementation gaps (state loss, OOM, GPS trust, unused retry infra) that will surface hardest on real devices |
| Testing | 71/100 | Backend integration suite is genuinely real and strong; Android has two tests that protect nothing; a few real gaps in double-submit coverage |
| Performance | 80/100 | No real problems at today's scale; the team already self-acknowledges most N+1 patterns in code comments |
| Reliability | 68/100 | Import pipeline is excellent; payment double-submit and territory-delete-crash are real, reproducible production landmines |
| Maintainability | 70/100 | Hurt by 3x/2x/2x duplicated business-rule implementations and dead-code residue across all three platforms |
| Production readiness | 55/100 | No CI/CD, no deployment docs, no Android crash reporting, unsigned release build, always-mounted API docs |

**Overall Engineering Health Score: 70/100** — a solid, thoughtfully-built core with real, specific, well-understood gaps standing between it and a safe production launch. Not a rewrite candidate; a fix-list candidate.

---

## 20. Production Readiness Assessment

**Not production-ready as of this audit**, specifically because of the five P0 items in §18 — every one of which is concrete, evidenced, and fixable without a redesign. **Production-ready once those five are closed**, with the P1 list closed shortly after as the second wave.

Separately from code fixes, the following are **process/infrastructure gaps** with no code fix possible from this audit alone: no CI/CD pipeline exists, no Dockerfile/deployment runbook exists, and the Android release build has no signing configuration at all. These need to be established before any real deployment, independent of the engineering fixes above.

---

## 21. Recommended Next 30/60/90 Day Engineering Plan

**Days 1-30 — Close the P0 list.** All five P0 items in §18. Two (P0-1, P0-4) need a short product-decision conversation before implementation starts; the other three (P0-2, P0-3, P0-5) can start immediately. In parallel, stand up a minimal CI pipeline (lint + test on every push) — currently absent and cheap to add now while the P0 fixes are being reviewed.

**Days 31-60 — Close the P1 list**, in this rough order: the four Android real-device-dependent items (state loss, geofence leak, GPS staleness, photo OOM) first, since they need physical-device verification time; the backend hardening items (docs-gating, security headers, rate-limiter, secret separation) in parallel, since they're independent and low-effort; the web bugs (autosave race, blob leak, report refetch) alongside, since they're isolated to single files each.

**Days 61-90 — Work through P2.** Consolidate the duplicated business-rule implementations (§15); add the missing indexes/constraints; wire up Android crash reporting; correct the misleading docs identified in §14; write the two missing design-decision docs (form versioning, payment trust workflow) while the context is still fresh. Establish a deployment runbook and Android release-signing configuration if a real release is imminent by this point.

---

## 22. Appendix — Files/Modules Inspected

**Backend** (`fieldtrackpro-backend/`): all files under `app/api/v1/`, `app/services/`, `app/repositories/`, `app/models/`, `app/schemas/`, `app/core/`, `app/exceptions/`, `app/jobs/`, `app/middleware.py`, `app/main.py`, `app/config.py`, `app/database.py`; all 12 files under `alembic/versions/`; representative files under `tests/` and all 27 files under `tests/integration/`; stray root log files.

**Web** (`fieldtrackpro-web/`): `App.tsx`, `src/api/client.ts`, `src/types/index.ts`, all 27 files under `src/pages/`, shared components under `src/components/ui/` and `src/components/forms/`, `AuthContext`, `FieldTrackMap.tsx`, `pdf-report.ts`, `phoneValidation.ts`, `package.json`.

**Android** (`fieldtrackpro-android/`): `ui/navigation/Screen.kt` and `NavGraph.kt`, all files under `data/api/`, `data/model/`, `data/repository/`, `data/local/`, `ui/viewmodel/`, `ui/screens/` (visits, requirements/forms, media, checkin/checkout, profile), `geofencing/`, `services/LocationCaptureService.kt`, `workers/`, `MainActivity.kt`, `AndroidManifest.xml`, `app/build.gradle.kts`, all 18 files under `app/src/test/`.

**Documentation**: repo-root `README.md`, `fieldtrackpro-backend/README.md`, `fieldtrackpro-android/README.md`, and a representative sample of `docs/` including `MASTER_REVERSE_ENGINEERING_CHECKLIST.md`, `final_forensic_audit/11_FINAL_VERDICT.md`, `phase_06_maps_geospatial/05_COMPLETION_REPORT.md`, `forensic_audits/maps_visibility/03_FINDINGS.md`, `repairs/maps_visibility/04_COMPLETION_REPORT.md`, `repairs/requirement_form_android/01_REQUIREMENT_FORM_REPAIR.md`, `P1_TALLY_INTEGRATION_INVESTIGATION.md`, `P1_EXCEL_MIS_IMPORT_ARCHITECTURE.md`, `ADVERSARIAL_FRAUD_AUDIT.md`, `REPAIR_CLOSURE_REPORT.md`, `FINAL_REPAIR_FORENSIC_REPORT.md`.

---

## "IF WE SHIPPED THIS TODAY" — Executive Conclusion

**What is safe**: the visit/media/signature/payment-read/form-submission authorization model; the data model's historical-integrity guarantees (immutable invoices, version-snapshotted submissions); the Excel import pipeline's atomicity and dedup behavior; the backend's real, DB-backed integration test suite; the web app's error/loading/empty-state discipline and shared component library.

**What is risky**: the unscoped customer/outlet directory (any employee can read the entire outlet list nationwide); payment creation with no duplicate-submission protection; Android's production API-override screen combined with app-wide cleartext traffic; Android's ungated manual GPS entry, which can defeat the app's core anti-fraud purpose entirely when combined with the customer-directory leak.

**What is ugly but acceptable for now**: the three-way duplication of the visit-ownership check; the two coexisting backend query patterns (repo vs. inline); several self-acknowledged N+1 patterns that don't yet matter at current data volumes; the stale `'MANAGER'` role residue on web/Android; the outdated documentation in `docs/` (misleading if trusted blindly, but the live code itself is not affected by it).

**What must be fixed before shipping**: the five P0 items in §18 — none require a redesign, all are evidenced and scoped, two need a short product conversation first.

**What should not be touched**: the visit/payment/form ownership pattern, the form-versioning design, the Excel import pipeline, the web shared-component library, the Android DTO contract-test suite — see §17 for the full list.

**What needs real-device/client-data verification before sign-off**: every Android state-loss, OOM, and geofence-leak finding in §8/§18 — these are exactly the class of bug that can look fine in an emulator and fail hard on a real device in a real field shift; the hand-rolled PDF exporter's behavior with non-ASCII (e.g. non-Latin-script) names in report data; the actual deployment topology's effect on the rate-limiter finding (single-worker vs. multi-worker changes whether P1-3 is urgent).

**Recommendation: LIMITED PILOT, not full production, not no-go.** The foundation is genuinely sound — this is not a codebase that needs to be rewritten or that has systemic architectural rot. But shipping to real field reps handling real outlet data and real money before closing the five P0 items would mean knowingly shipping a data-privacy leak, a financial double-counting risk, and a set of Android gaps that could undermine the product's core value proposition (verified visits) on day one. Close the P0 list — a matter of days to low weeks of focused work, not months — then proceed to a full rollout with the P1 list tracked as an immediate follow-up.
