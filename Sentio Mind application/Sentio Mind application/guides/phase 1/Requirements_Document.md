# Requirements Document
### Phase 1.1 — Product Discovery & Planning

---

## 1. Functional Requirements

### 1.1 Authentication & Access Control
- FR-1: Employees can log in using email or mobile number + password.
- FR-2: Managers/Admins log in through a separate web-based authentication flow.
- FR-3: System supports role-based access control (RBAC) with at least two roles: `EMPLOYEE`, `ADMIN`.
- FR-4: Sessions are managed via JWT access + refresh tokens (OAuth2-compliant).
- FR-5: Passwords are stored hashed (bcrypt/Argon2) — never in plain text.
- FR-6: Failed login attempts are rate-limited to prevent brute force.

### 1.2 Employee Mobile App
- FR-7: Employee sees a dashboard of assigned visits for the current day.
- FR-8: Each visit shows customer name, address, contact, and location pin.
- FR-9: Employee can open the customer location directly in Google Maps for turn-by-turn navigation.
- FR-10: App captures the employee's live GPS coordinates during an active visit.
- FR-11: App verifies the employee is within a configurable radius (default 50–100m, admin-adjustable) of the customer location before allowing check-in.
- FR-12: Geo-fence auto-triggers a check-in prompt when the employee physically enters the boundary.
- FR-13: Attendance/visit-start is marked **only** after successful location verification — no manual override for employees.
- FR-14: Employee can capture customer requirements via a structured form *(fields pending confirmation — see Section 4)*.
- FR-15: Employee can attach photos and documents to a visit record.
- FR-16: Employee can capture both customer and employee digital signatures at visit completion.
- FR-17: Employee can submit the completed visit record, which syncs to the backend.
- FR-18: App functions in offline mode — visit data is cached locally and synced when connectivity returns.
- FR-19: Employee receives push notifications for new/updated visit assignments.

### 1.3 Admin / Manager Web Dashboard
- FR-20: Admin can create, edit, deactivate employee accounts and assign territories.
- FR-21: Admin can create and manage customer records (name, location, contact, notes).
- FR-22: Admin can schedule and assign visits to employees.
- FR-23: Admin can view a live map of all employees' current/last-known locations.
- FR-24: Admin can monitor visit status in real time: not started / in progress / completed / missed.
- FR-25: Admin can view and export reports *(exact report set pending confirmation — see Section 4)*.
- FR-26: Admin can view per-employee productivity metrics (visits completed, distance traveled, average visit duration).

### 1.4 Notifications
- FR-27: System sends notifications for: new visit assigned, visit reminder, visit overdue, visit completed.
- FR-28: Admin receives an alert if an employee's check-in fails geo-fence verification repeatedly.

---

## 2. Non-Functional Requirements

| Category | Requirement |
|---|---|
| **Security** | All API traffic over HTTPS/TLS. JWT-based auth. Role-based authorization enforced server-side, not just client-side. |
| **Performance** | GPS check-in verification should resolve in under 3 seconds under normal network conditions. |
| **Availability** | Backend targets 99% uptime during business hours (on-prem, so tied to infra SLAs). |
| **Offline Support** | Mobile app must queue visit data locally and sync automatically without data loss when back online. |
| **Scalability** | Backend should handle growth from pilot (tens of employees) to enterprise scale (hundreds+) without architecture rework. |
| **Data Retention** | Visit records, photos, and signatures retained indefinitely unless a retention policy is defined later. |
| **Usability** | Employee app flow (login → visit → check-in → capture → submit) should be completable in under 5 taps/screens per step. |
| **Auditability** | Every visit record logs timestamp, GPS coordinates at check-in, and verification status — immutable once submitted. |
| **Compatibility** | Android app targets a minimum OS version to be defined (recommend Android 8.0+ for GPS/geofencing API stability). |

---

## 3. User Roles

| Role | Access |
|---|---|
| **Employee** | Mobile app only. Own assigned visits. No access to other employees' data. |
| **Admin/Manager** | Web dashboard. Full access to employees, customers, visits, reports within their org/territory. |
| *(Future)* **Super Admin** | Multi-org/tenant management — not in MVP scope. |

---

## 4. Open Questions — Require Confirmation Before Phase 2

These were flagged in the original proposal as pending sign-off. Locking these now prevents rework later:

1. **Customer Requirement Capture form** — exact fields needed beyond the draft list (customer name/contact, requirement category, notes, budget, timeline, product/service needed). Any mandatory vs. optional fields? Any dropdown/category taxonomy to predefine?
2. **Reports & Analytics scope** — which specific reports are must-have for MVP vs. nice-to-have (e.g., is "distance travelled" cost-relevant, or just tracking)?
3. **GPS tracking cost** — proposal notes "cost analysis?" next to GPS tracking. Is continuous live tracking required, or only point-in-time verification at check-in? This significantly affects battery usage, data costs, and backend load.
4. **Cloud storage** — proposal states "on-prem." Confirm infra availability for storing photos/documents/signatures before Phase 5 (File & Media Management) begins.

---

## 5. Out of Scope for MVP

Explicitly deferred to the Future Roadmap (do not build in Phases 1–10):
- AI-generated visit summaries or productivity insights
- Automatic route optimization across multiple visits
- ERP/CRM integrations
- Face verification for check-in
- Voice note capture
- Advanced offline-sync conflict resolution beyond basic queue-and-sync

---

**Next up:** User Flows (Phase 1.2) — mapping the actual screen-by-screen journey for Employee and Admin, which will directly inform the UI/UX work in Phase 6 and Phase 7.