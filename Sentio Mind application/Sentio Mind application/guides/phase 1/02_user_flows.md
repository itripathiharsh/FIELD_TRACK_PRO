# FieldTrack Pro — User Flows
### Phase 1.2 — Product Discovery & Planning

Two primary actors: **Employee** (Android app) and **Admin/Manager** (Web dashboard). Flows below are screen-by-screen so they map directly to Phase 6 (Android) and Phase 7 (Admin Dashboard) build work.

---

## 1. Employee Flow — Android App

### 1.1 Login
1. Splash screen → Login screen (email/mobile + password).
2. On success → token stored securely (encrypted local storage) → redirect to Dashboard.
3. On failure → inline error, rate-limited after repeated attempts (FR-6).

### 1.2 Dashboard (Home)
1. Employee lands on **Today's Visits** list — cards showing customer name, address, scheduled time, status (Pending / In Progress / Completed / Missed).
2. Pull-to-refresh syncs latest assignments from server.
3. Tapping a visit card opens **Visit Detail**.

### 1.3 Visit Detail → Navigation
1. Shows customer info, location pin on embedded map, contact button (call/SMS).
2. **"Navigate"** button opens Google Maps app with turn-by-turn directions to customer location (FR-9).
3. **"Start Visit"** button is disabled until employee is within the geo-fenced radius.

### 1.4 Geo-fence Check-in
1. App continuously checks device GPS against customer geo-fence radius while Visit Detail screen is open.
2. On entering radius → auto-prompt: *"You've arrived at [Customer]. Check in?"* (FR-12).
3. Employee confirms → GPS coordinates + timestamp logged → visit status becomes **In Progress** (FR-13).
4. If GPS fails/denied → clear error state: *"Location permission required to check in"* with a retry action. No manual bypass for the employee.

### 1.5 Requirement Capture
1. Structured form opens automatically after check-in (fields per Requirements doc Section 4.1).
2. Form auto-saves locally as employee fills it (protects against app kill/crash).
3. Employee can attach photos (camera or gallery) and documents (FR-15).

### 1.6 Signature Capture
1. After form completion, employee taps **"Complete Visit."**
2. Two signature pads shown in sequence: Employee signature, then Customer signature (FR-16).
3. Both required before submission is allowed.

### 1.7 Submission & Sync
1. On submit → visit record marked **Completed** locally, status changes on Dashboard immediately.
2. If online → syncs to backend instantly.
3. If offline → record queues locally, syncs automatically on reconnect (FR-18), with a visible "Pending Sync" badge on the visit card.

### 1.8 Notifications
1. Push notification on new visit assignment, visit reminder (e.g., 30 min before scheduled time), and overdue alert if a visit hasn't started past its scheduled window (FR-27).

---

## 2. Admin/Manager Flow — Web Dashboard

### 2.1 Login
1. Admin login screen (separate auth flow from employee app, FR-2).
2. On success → redirect to **Overview Dashboard**.

### 2.2 Overview Dashboard
1. Summary cards: Total employees active today, visits scheduled/completed/missed, geo-verification flags needing review.
2. Live map showing last-known employee locations, pinned at their most recent check-in/check-out (per the point-in-time tracking decision).

### 2.3 Employee Management
1. List view of all employees → search/filter by territory/status.
2. **Add Employee** → form (name, contact, login credentials, assigned territory).
3. **Edit/Deactivate Employee** → toggles access without deleting historical visit data.

### 2.4 Customer Management
1. List view of all customers → search/filter.
2. **Add Customer** → form (name, contact, address, auto-geocoded location pin, geo-fence radius override if needed).
3. Customer detail page shows full visit history (ties into Reports).

### 2.5 Visit Scheduling & Assignment
1. Admin creates a visit → selects Customer + Employee + scheduled date/time.
2. Bulk assignment option for recurring/multiple visits.
3. Visit appears instantly on the assigned employee's mobile Dashboard.

### 2.6 Visit Monitoring
1. Real-time visit status board (Kanban-style: Pending / In Progress / Completed / Missed / Flagged).
2. Clicking a visit shows full detail: captured requirement form, photos, signatures, GPS check-in coordinates and verification status.
3. **Flagged visits** (failed geo-verification, per FR-28) surfaced prominently for admin review.

### 2.7 Reports & Analytics
1. Four report tabs per the locked decision: Employee Visit Report, Customer Visit History, Productivity Dashboard, Geo-verification Report.
2. Each report supports date-range filtering and CSV/PDF export.
3. Productivity Dashboard shows per-employee charts: visits/day, avg. visit duration, distance traveled.

---

## 3. Cross-Cutting Flow — Offline → Online Sync

This isn't a screen, but it's a flow that touches both Employee app and backend, worth calling out separately since it's a common failure point:

1. Employee completes visit while offline → record stored in local DB (Room/SQLite) with a `synced: false` flag.
2. App detects connectivity restored (network listener) → background sync job pushes queued records to backend one by one.
3. Backend acknowledges each record → app updates `synced: true`, removes "Pending Sync" badge.
4. If a sync conflict occurs (rare — e.g., visit reassigned while offline) → server response flags it, admin dashboard surfaces it under Flagged for manual resolution.

---

**Next up:** Features (Phase 1.3) — turning these flows into a discrete, buildable feature list mapped to each phase, which becomes your actual Antigravity task backlog.
