# FieldTrack Pro — Definition of Done (Feature Verification)
### Every feature from 03_features.md, verified end-to-end — API working is NOT enough

**Rule: "No means no."** A feature is only DONE if it passes both columns below. An API returning 200 with a UI that doesn't reflect it, save it, or let a real user complete the flow is **NOT DONE** — mark it FAIL and send it back. Partial credit doesn't exist in this doc; a feature is either fully working end-to-end or it isn't.

Use this as a literal checklist. For each row: test the API call directly (Postman/curl), then test the same thing by tapping/clicking through the actual app/dashboard as a real user would, then check the database to confirm the data actually landed correctly. All three must agree.

---

## Module A — Authentication & Access Control

| ID | Feature | API Check | UI Check | Pass Criteria |
|---|---|---|---|---|
| A1 | Employee login | `POST /auth/login` returns tokens | Login screen accepts credentials, navigates to Dashboard | Both succeed with same credentials; wrong password shows error in UI, not a silent failure |
| A2 | Admin login | Same, admin role | Admin login screen → Dashboard Overview | Role-specific redirect actually happens, not generic |
| A3 | JWT tokens | Access token expires per config, refresh works | App silently refreshes without logging user out mid-session | Sit on a screen past token expiry — confirm no forced logout, no visible interruption |
| A4 | Password hashing | DB `password_hash` column is not plaintext/reversible | N/A (backend-only) | `SELECT password_hash FROM users` shows a bcrypt/Argon2 hash, never the raw password |
| A5 | RBAC | Employee token hitting admin endpoint → 403 | Employee app has no way to reach admin screens even by deep-link/URL manipulation | Try manually navigating an employee session to an admin route — must be blocked, not just hidden |
| A6 | Rate limiting | 6th failed login attempt in 15 min → 429 | Login screen shows a real message, not a generic error | Actually fail login 6 times in a row and watch it happen — don't just trust the code exists |
| A7 | Secure token storage | N/A | Pull app data via ADB on a non-rooted test device — token should not be readable in plaintext | Confirms Android Keystore encryption is actually active, not just configured |

---

## Module B — Employee Management

| ID | Feature | API Check | UI Check | Pass Criteria |
|---|---|---|---|---|
| B1 | Create/edit/deactivate | `POST/PUT/PATCH /employees` all work | Admin can add an employee via the form and see it appear in the list without refresh | New employee can immediately log in on Android with the credentials just created |
| B2 | Territory assignment | Employee record has `territoryId` | Territory shows correctly on Employee Detail page | Assign a territory, confirm it's reflected everywhere the employee appears |
| B3 | Employee list UI | `GET /employees` with filters | List/search/filter actually filters visually, not just accepts params silently | Search for a name that doesn't exist → empty state shows, not a blank screen or crash |
| B4 | Add/edit employee form | — | Form validation matches backend validation | Submit an invalid form (bad email) client-side AND bypass client validation via API — both should reject it |

---

## Module C — Customer Management

| ID | Feature | API Check | UI Check | Pass Criteria |
|---|---|---|---|---|
| C1 | Create/edit customer | `POST/PUT /customers` | Form works, list updates | New customer immediately schedulable for a visit |
| C2 | Auto-geocode | Address-only payload returns populated lat/long | Map pin appears in the correct real-world location, not (0,0) or null-island | Test with a real, verifiable address — confirm the pin is actually correct, not just non-null |
| C3 | Geofence radius config | `geofenceRadiusM` accepted and stored | Radius field editable in Add/Edit Customer form | Change radius, then actually attempt a check-in at the new boundary distance — confirm it respects the new value, not a cached old one |
| C4 | List with search/filter | `GET /customers` filters work | Same as B3 pattern | Empty state and populated state both render correctly |
| C5 | Add/edit form | — | Map picker toggle works (per Web Dashboard doc Section 3) | Both address-geocode path AND manual pin-drop path produce a valid, correct location |
| C6 | Customer detail + visit history | `GET /customers/{id}/visits` | Detail page renders visit list | Complete a real visit for this customer, refresh the page, confirm it appears |

---

## Module D — Visit Scheduling & Assignment

| ID | Feature | API Check | UI Check | Pass Criteria |
|---|---|---|---|---|
| D1 | Create visit | `POST /visits` | Schedule form works | Visit appears on the assigned employee's Android Dashboard — this is the real test, not just a 201 response |
| D2 | Bulk/recurring assignment | `POST /visits/bulk` | Bulk scheduling UI produces the right number of visit records | Count the actual rows created against what was requested — off-by-one errors hide easily here |
| D3 | Status state machine | Invalid transitions rejected (e.g. COMPLETED→PENDING) | Status badge in UI always matches DB state | Force an invalid transition via direct API call — confirm it's rejected, not just discouraged by the UI |
| D4 | Scheduling form | — | Form UX matches wireframe intent | Real admin can schedule a visit in under the target number of steps without confusion |
| D5 | Status board (Kanban) | `GET /visits` with status filter | Cards move columns as status genuinely changes (via real check-in, not manual DB edit) | Do a real check-in on Android, watch the Web board update within its polling interval — don't just seed fake data |

---

## Module E — GPS & Geofencing (Highest-Stakes Module — Test Thoroughly)

| ID | Feature | API Check | UI Check | Pass Criteria |
|---|---|---|---|---|
| E1 | Geofence radius check service | `ST_DWithin` query returns correct true/false at real coordinates | — | Test at a point exactly on the boundary, just inside, just outside — confirm correct classification at all three |
| E2 | Distance calculation | `ST_Distance` returns accurate meters | Distance shown in Flagged Visit Review matches | Compare against a known real-world distance (e.g., measured on Google Maps) — should be close, not wildly off |
| E3 | Continuous polling while screen active | — | Android app actually reads live GPS while Visit Detail is open | Walk toward a real customer location with the screen open — confirm it detects proximity in real time |
| E4 | Auto-trigger on geofence entry | — | Check-in prompt actually appears automatically on physical arrival | This must be tested by physically walking into the geofence radius, not simulated in an emulator only |
| E5 | Server-side verification (NON-NEGOTIABLE) | Send a check-in request with **fabricated** coordinates that are clearly outside radius, bypassing the app entirely (raw API call) | — | Must be rejected with 422 — if a raw API call with fake "inside radius" coordinates from a location the tester is NOT physically at gets accepted, **this is an automatic FAIL of the entire module**, regardless of how well everything else works |
| E6 | Failed-verification handling | 422 response has clear reason code | Retry screen shows accordingly, not a generic crash/error | Fail a check-in on purpose, confirm the UI degrades gracefully with the exact copy from User Journey doc |
| E7 | Geo-verification flagging | 3 failures → status FLAGGED | Flagged badge appears on both Android (if visible) and Web | Actually trigger 3 real failures in sequence, confirm the flag fires exactly at 3, not 2 or 4 |

---

## Module F — Maps & Navigation

| ID | Feature | API Check | UI Check | Pass Criteria |
|---|---|---|---|---|
| F1 | Maps SDK integration | — | Map renders on Visit Detail, no blank/gray tile errors | Test on real device, real network — SDK/API key issues often only show in production builds |
| F2 | Navigate deep link | — | Tapping Navigate opens Google Maps app with correct destination pre-filled | Confirm the actual destination pin matches the customer's real location, not a stale/wrong coordinate |
| F3 | Admin live map | `GET /dashboard/live-map` | Pins render at correct last-known locations | Do a real check-in, confirm the admin map pin updates (within polling interval) — not showing a stale/default position |
| F4 | Marker clustering | — | Multiple nearby employees cluster visually instead of overlapping illegibly | Test with several visits scheduled close together geographically |

---

## Module G — File & Media Management

| ID | Feature | API Check | UI Check | Pass Criteria |
|---|---|---|---|---|
| G1 | Image upload | `POST /visits/{id}/media` accepts, compresses | Photo picker → upload → thumbnail appears | Uploaded image is actually retrievable and viewable afterward, not just "upload succeeded" |
| G2 | Document upload | Same for PDFs/docs | Document picker works, shows in attachment list | Download/view the uploaded doc afterward — confirm it's not corrupted |
| G3 | Signature capture component | — | Canvas actually captures a legible signature, not garbled strokes | Have a real person sign, confirm the resulting image is recognizably a signature |
| G4 | Signature storage linked to visit | `POST /visits/{id}/signatures` | Both signatures appear correctly attributed (EMPLOYEE vs CUSTOMER) | Attempt to submit two EMPLOYEE signatures for the same visit — must be rejected (per the uniqueness fix) |
| G5 | File validation | Upload a renamed `.exe` as `.jpg` | — | Must be rejected by magic-byte detection (`python-magic`), not accepted because the extension looked right |

---

## Module H — Requirement Capture Form

| ID | Feature | API Check | UI Check | Pass Criteria |
|---|---|---|---|---|
| H1 | Dynamic form renderer | — | All fields from the locked field list render and accept input | Cross-check against Requirements doc Section 4.1 field list — nothing missing, nothing extra |
| H2 | Category dropdown (admin-editable) | `GET /requirement-categories` reflects admin additions | New admin-added category appears in Android dropdown without app update | Add a category via Web, confirm it shows up on Android on next load |
| H3 | Local auto-save | — | Force-close the app mid-form, reopen, draft is restored | This must be tested by actually killing the app process, not just backgrounding it |
| H4 | Form submission linked to visit | `GET /visits/{id}/requirement-form` returns submitted data | Submitted form is viewable from Admin's Visit Detail page | Data matches exactly what was typed, no field silently dropped |

---

## Module I — Android Core App

| ID | Feature | API/Data Check | UI Check | Pass Criteria |
|---|---|---|---|---|
| I1 | Splash + login | — | Existing valid token skips login, expired token routes to login | Test both cold-start states explicitly |
| I2 | Dashboard | `GET /visits/me/today` | List renders with correct status badges | Cross-check every visit's displayed status against its actual DB status |
| I3 | Visit Detail screen | — | All customer info renders correctly | — |
| I4 | Pull-to-refresh | — | Gesture actually re-fetches, visible loading state | Change data server-side, pull-to-refresh, confirm it reflects the change |
| I5 | Push notifications | FCM token registered | Notification actually arrives on a real device | Test on a real device with the app backgrounded/killed, not just foregrounded in a debugger |
| I6 | Offline local DB | — | Complete a visit in airplane mode, data persists in Room | Force-kill the app while offline data is queued, reopen, confirm it's still there |
| I7 | Background sync (WorkManager) | Server receives the queued data eventually | "Pending Sync" clears automatically on reconnect | Must work without reopening the app — WorkManager should fire in the background |
| I8 | Sync/conflict UI badges | — | Badge accurately reflects sync state at all times | No false "synced" badge on data that actually failed to reach the server |

---

## Module J — Admin Web Dashboard Core

| ID | Feature | Check |
|---|---|---|
| J1 | Overview dashboard | Summary counts match actual DB counts exactly — recount manually and compare |
| J2 | Navigation shell | Every sidebar link goes to a working page, no dead links/404s |
| J3 | Role-based UI gating | N/A for MVP (single ADMIN role) — confirm nothing broke assuming future roles |

---

## Module K — Reports & Analytics

| ID | Feature | API Check | UI Check | Pass Criteria |
|---|---|---|---|---|
| K1 | Employee Visit Report | `GET /reports/employee-visits` | Table renders, filters work | Numbers match a manual count from the DB for a known test period |
| K2 | Customer Visit History | Same pattern | — | — |
| K3 | Productivity Dashboard | Aggregation query correct | Charts render correctly, "approx." label present on distance | Verify the "approx." copy is actually there, not dropped during UI build |
| K4 | Geo-verification Report | Flagged/failed entries listed | Reason codes human-readable, not raw enum strings | A non-technical admin should understand each row without explanation |
| K5 | Date-range filtering | Params respected | Date picker UI actually constrains the query | Pick a range with zero visits — confirm empty state, not an error |
| K6 | CSV/PDF export | Export endpoint returns valid file | Download button works, file opens correctly | Actually open the exported file — confirm it's not corrupted and matches on-screen data |

---

## Module L — Notifications

| ID | Feature | Check |
|---|---|---|
| L1 | Notification service triggers | Every event type (new visit, reminder, overdue, completed, geo-alert) actually fires — test each one individually, don't assume the pattern holds for all five just because one works |
| L2 | FCM delivery | Real device, app backgrounded — notification arrives within a reasonable delay |
| L3 | Notification types render correctly | Each type has distinct, correct copy — not a generic "You have a notification" for everything |
| L4 | Admin alert on repeated failures | Trigger 3 real geo-verification failures, confirm an admin actually receives the alert, not just a DB row with no delivery |

---

## Cross-Cutting End-to-End Scenarios (Beyond Individual Features)

These aren't single features — they're full user journeys that must work start to finish, matching the Integration Testing scenarios from Phase 8:

- [ ] A brand-new employee, created by an admin from scratch, can log in and see a scheduled visit within 5 minutes of account creation — no manual DB intervention required.
- [ ] A complete visit — navigate, check in, fill form, attach photo, capture both signatures, check out — works start to finish on a real device against the real backend, and every piece of data from that visit is visible and correct on the Admin dashboard afterward.
- [ ] The same flow, but performed entirely offline until the very end, still produces identical correct data once synced.
- [ ] A deliberately fraudulent check-in attempt (fabricated coordinates, mock location) is caught and flagged, and an admin can see exactly why.

---

## How to Use This Doc

1. Go module by module, feature by feature.
2. Do not mark anything DONE from code review alone — every row requires an actual executed test (API call + UI interaction + DB check, as applicable).
3. Anything marked FAIL goes back to the relevant phase doc, gets fixed, gets retested from scratch — not just re-checked at the point of failure, since a fix can introduce a new regression elsewhere.
4. **E5 is the one row in this entire document where a FAIL should stop everything else** — it's the actual security foundation the whole product depends on. Don't let a passing UI demo distract from a failing E5.
