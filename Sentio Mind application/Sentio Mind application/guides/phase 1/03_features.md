# FieldTrack Pro — Features
### Phase 1.3 — Product Discovery & Planning

Discrete, buildable features derived from Requirements + User Flows. Each is scoped small enough to become an individual Antigravity prompt later. Grouped by module, tagged with which build Phase they belong to (per the corrected 10-phase plan) so this doc doubles as your backlog.

---

## Module A: Authentication & Access Control (Phase 3)
- A1. Employee login (email/mobile + password)
- A2. Admin login (separate flow)
- A3. JWT access + refresh token issuance
- A4. Password hashing (bcrypt/Argon2)
- A5. Role-based authorization middleware (EMPLOYEE / ADMIN)
- A6. Login rate-limiting / brute-force protection
- A7. Secure token storage on Android (encrypted shared prefs / Keystore)

## Module B: Employee Management (Phase 3 + Phase 7 UI)
- B1. Create/edit/deactivate employee (backend API)
- B2. Assign employee to territory
- B3. Admin UI: employee list with search/filter
- B4. Admin UI: add/edit employee form

## Module C: Customer Management (Phase 3 + Phase 7 UI)
- C1. Create/edit customer record (backend API)
- C2. Auto-geocode customer address → lat/long
- C3. Configurable geo-fence radius per customer (default 50–100m)
- C4. Admin UI: customer list with search/filter
- C5. Admin UI: add/edit customer form
- C6. Customer detail page with visit history

## Module D: Visit Scheduling & Assignment (Phase 3 + Phase 7 UI)
- D1. Create visit (customer + employee + datetime) — backend API
- D2. Bulk/recurring visit assignment
- D3. Visit status state machine: Pending → In Progress → Completed / Missed / Flagged
- D4. Admin UI: visit scheduling form
- D5. Admin UI: real-time visit status board (Kanban view)

## Module E: GPS & Geofencing (Phase 4)
- E1. Geo-fence radius check service (backend)
- E2. Distance calculation utility (Haversine or Maps API)
- E3. Android: continuous GPS polling while Visit Detail screen active
- E4. Android: auto-trigger check-in prompt on geo-fence entry
- E5. Check-in verification endpoint (validates GPS coords server-side, not just client-side)
- E6. Failed-verification handling + retry flow
- E7. Geo-verification flagging logic (for admin review)

## Module F: Maps & Navigation (Phase 4)
- F1. Google Maps SDK integration (Android)
- F2. "Navigate to customer" deep link into Google Maps app
- F3. Admin dashboard live map (last-known location pins)
- F4. Map marker clustering for admin view (multiple employees/customers)

## Module G: File & Media Management (Phase 5)
- G1. Image upload endpoint + storage (on-prem object storage, e.g. MinIO)
- G2. Document upload endpoint + storage
- G3. Digital signature capture component (Android — canvas/pad)
- G4. Signature storage as image, linked to visit record
- G5. File size/type validation + compression before upload

## Module H: Requirement Capture Form (Phase 6)
- H1. Dynamic form renderer (Android) per locked field list
- H2. Requirement category dropdown (admin-editable taxonomy)
- H3. Local auto-save while filling form (crash protection)
- H4. Form submission → linked to visit record

## Module I: Android Core App (Phase 6)
- I1. Splash + login screens
- I2. Today's Visits dashboard (list + status badges)
- I3. Visit Detail screen
- I4. Pull-to-refresh sync
- I5. Push notification handling (new visit, reminder, overdue)
- I6. Offline local DB (Room/SQLite) for visit queueing
- I7. Background sync job (offline → online)
- I8. "Pending Sync" UI badge + conflict flagging

## Module J: Admin Web Dashboard Core (Phase 7)
- J1. Overview dashboard (summary cards: active employees, visits today, flags)
- J2. Navigation shell / layout
- J3. Role-based UI gating (in case future roles are added)

## Module K: Reports & Analytics (Phase 7)
- K1. Employee Visit Report (visits completed/missed per employee/period)
- K2. Customer Visit History report
- K3. Productivity Dashboard (visits/day, avg duration, distance traveled)
- K4. Geo-verification Report (flagged check-ins)
- K5. Date-range filtering across all reports
- K6. CSV/PDF export

## Module L: Notifications (Phase 3 backend + Phase 6 Android)
- L1. Notification service (backend — triggers on visit events)
- L2. Push notification delivery (FCM integration)
- L3. Notification types: new visit assigned, reminder, overdue, completed
- L4. Admin alert on repeated geo-verification failures

---

## Feature Count Summary

| Module | Feature Count | Primary Phase |
|---|---|---|
| A — Auth | 7 | 3 |
| B — Employee Mgmt | 4 | 3 / 7 |
| C — Customer Mgmt | 6 | 3 / 7 |
| D — Visit Scheduling | 5 | 3 / 7 |
| E — GPS & Geofencing | 7 | 4 |
| F — Maps & Navigation | 4 | 4 |
| G — File & Media | 5 | 5 |
| H — Requirement Form | 4 | 6 |
| I — Android Core | 8 | 6 |
| J — Admin Core | 3 | 7 |
| K — Reports & Analytics | 6 | 7 |
| L — Notifications | 4 | 3 / 6 |
| **Total** | **63** | — |

This 63-item list is your MVP scope boundary — everything from the proposal is represented, nothing extra. Anything not listed here belongs to the Future Roadmap doc, not MVP.

---

**Next up:** Tech Stack (Phase 1.4) — locking the actual frameworks/libraries/services for each module above, so Phase 2 (System Design) has something concrete to design against.
