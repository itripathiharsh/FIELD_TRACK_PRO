# FieldTrack Pro — Web Dashboard Screen List
### Phase 2.5 — UX & Wireframes (continued)

Every screen the Admin Web Dashboard needs, derived from User Flows (Section 2) and Features (Modules B/C/D/J/K). Same traceability approach as the Android list — each screen tagged to the feature IDs it fulfills.

---

## 1. Auth Flow

| # | Screen | Purpose | Feature Refs |
|---|---|---|---|
| 1 | Admin Login | Email + password, separate auth flow from employee app | A2 |

---

## 2. Overview / Home

| # | Screen | Purpose | Feature Refs |
|---|---|---|---|
| 2 | Dashboard Overview | Summary cards (active employees, visits today, flagged count) + live map | J1 |
| 3 | Live Map (full view) | Expanded map view — last-known employee locations, clustered markers | F3, F4 |

---

## 3. Employee Management

| # | Screen | Purpose | Feature Refs |
|---|---|---|---|
| 4 | Employee List | Searchable/filterable table (by territory, active status) | B3 |
| 5 | Add Employee | Form: name, contact, login credentials, territory assignment | B1 |
| 6 | Edit Employee | Same form pre-filled, includes deactivate action | B1, B2 |
| 7 | Employee Detail | Read view: profile + their visit history/stats | B3 |

---

## 4. Customer Management

| # | Screen | Purpose | Feature Refs |
|---|---|---|---|
| 8 | Customer List | Searchable/filterable table | C4 |
| 9 | Add Customer | Form: name, contact, address (auto-geocode), geofence radius override | C1, C2, C3 |
| 10 | Edit Customer | Same form pre-filled | C1, C3 |
| 11 | Customer Detail | Profile + full visit history (feeds Customer Visit History report) | C6 |

---

## 5. Visit Scheduling & Monitoring

| # | Screen | Purpose | Feature Refs |
|---|---|---|---|
| 12 | Visit List / Status Board | Kanban-style board: Pending / In Progress / Completed / Missed / Flagged | D3, D5 |
| 13 | Schedule Visit | Form: select customer + employee + datetime | D1, D4 |
| 14 | Bulk Schedule Visits | Recurring/multiple visit assignment in one action | D2 |
| 15 | Visit Detail (Admin view) | Full record: requirement form, photos, signatures, GPS check-in data, verification status | — (ties to E7, G4) |
| 16 | Flagged Visit Review | Focused view for visits with failed geo-verification, with reason codes | E7, security non-negotiable #4 |

---

## 6. Reports & Analytics

| # | Screen | Purpose | Feature Refs |
|---|---|---|---|
| 17 | Employee Visit Report | Table + filters (employee, date range) | K1, K5 |
| 18 | Customer Visit History Report | Table + filters (customer, date range) | K2, K5 |
| 19 | Productivity Dashboard | Charts: visits/day, avg duration, distance traveled per employee | K3 |
| 20 | Geo-verification Report | Table of flagged/failed check-ins with reason codes | K4 |
| 21 | Export Modal | Shared component across all report screens — CSV/PDF export trigger | K6 |

---

## 7. Territories & Settings

| # | Screen | Purpose | Feature Refs |
|---|---|---|---|
| 22 | Territory Management | List + add/edit territories, used in employee/customer assignment dropdowns | B2, C-territory link |
| 23 | Requirement Category Management | Admin-editable taxonomy for the requirement capture dropdown | H2 |
| 24 | Admin Settings | Account settings, logout | — |

---

## Screen Count Summary

| Flow Area | Screen Count |
|---|---|
| Auth | 1 |
| Overview | 2 |
| Employee Management | 4 |
| Customer Management | 4 |
| Visit Scheduling & Monitoring | 5 |
| Reports & Analytics | 5 |
| Territories & Settings | 3 |
| **Total** | **24** |

---

## Notes Worth Flagging Before Wireframing

- **Screen 16 (Flagged Visit Review)** is the screen that operationalizes your whole "eliminate fake visit reporting" pitch — worth giving it real design attention rather than treating it as just another table view. An admin should be able to see *why* something was flagged (out of radius vs. mock GPS vs. GPS unavailable) at a glance.
- **Screen 21 (Export Modal)** being a shared component rather than 4 separate export screens keeps the dashboard consistent and cuts build time — flagging so whoever builds this doesn't duplicate the logic per report.
- **Territory Management (22)** wasn't explicitly called out as its own screen in the User Flows doc, but it's a dependency for both Employee and Customer forms (both need a territory dropdown) — needs to exist before those two modules can be fully functional, so build order matters here even within Phase 7.

---

**Next up:** Actual wireframe layouts (low-fidelity) for the highest-priority screens — or straight into Phase 3 Backend Development if you'd rather skip visual wireframing and let Antigravity generate UI directly from these screen lists + the Tech Stack choices (Compose/shadcn already give strong default styling, so hand-drawn wireframes may be optional for this project).
