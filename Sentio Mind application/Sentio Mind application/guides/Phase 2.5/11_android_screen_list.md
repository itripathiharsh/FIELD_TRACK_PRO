# FieldTrack Pro — Android Screen List
### Phase 2.5 — UX & Wireframes

Every screen the Android app needs, derived directly from User Flows (Section 1) and Features (Modules E/G/H/I). Grouped by flow area, each tagged with the primary feature IDs it fulfills so nothing gets built that isn't traceable back to a requirement.

---

## 1. Auth Flow

| # | Screen | Purpose | Feature Refs |
|---|---|---|---|
| 1 | Splash Screen | Brief branding load, checks for existing valid token → routes to Login or Dashboard | A7 |
| 2 | Login Screen | Email/mobile + password input, error states, rate-limit messaging | A1, A6 |

---

## 2. Dashboard / Home Flow

| # | Screen | Purpose | Feature Refs |
|---|---|---|---|
| 3 | Today's Visits Dashboard | List of assigned visits with status badges (Pending/In Progress/Completed/Missed), pull-to-refresh | I2, I4 |
| 4 | Empty State — No Visits Today | Shown when dashboard list is empty (not a separate screen technically, but a distinct state worth designing intentionally) | I2 |
| 5 | Notifications List | List of push notifications received (new visit, reminder, overdue) | L3 |

---

## 3. Visit Flow

| # | Screen | Purpose | Feature Refs |
|---|---|---|---|
| 6 | Visit Detail | Customer info, map preview, Navigate + Start Visit buttons | I3 |
| 7 | Navigation Handoff | Not a custom screen — deep-links out to Google Maps app | F2 |
| 8 | Geo-fence Waiting / Arrival State | Shown while employee is en route but outside radius; transitions automatically to check-in prompt on entry | E3, E4 |
| 9 | Check-in Confirmation Dialog | "You've arrived — check in?" prompt | E4 |
| 10 | Check-in Failed / Retry State | Shown on failed geo-verification (out of radius, GPS unavailable) | E6 |

---

## 4. Requirement Capture Flow

| # | Screen | Purpose | Feature Refs |
|---|---|---|---|
| 11 | Requirement Form | Category dropdown, description, priority, timeline, budget, notes — auto-saves locally as filled | H1, H2, H3 |
| 12 | Photo/Document Attachment Picker | Camera capture or gallery/file picker, shows attached thumbnails | G1, G2 |
| 13 | Attachment Preview | Full-screen view of an attached photo/document before/after upload | G1, G2 |

---

## 5. Signature & Completion Flow

| # | Screen | Purpose | Feature Refs |
|---|---|---|---|
| 14 | Employee Signature Pad | Canvas-based signature capture, clear/retry option | G3, G4 |
| 15 | Customer Signature Pad | Same component, second instance, sequential after employee's | G3, G4 |
| 16 | Visit Summary / Review | Final review of form + attachments + signatures before submit | I3 |
| 17 | Submission Success State | Confirmation, visit status updates to Completed, returns to Dashboard | I3 |

---

## 6. Sync & Offline States

| # | Screen | Purpose | Feature Refs |
|---|---|---|---|
| 18 | Pending Sync Badge (in-list indicator) | Not a full screen — a persistent visual state on Dashboard visit cards while offline-queued | I6, I8 |
| 19 | Sync Conflict / Flagged Notice | Shown if a synced record comes back flagged (rare — reassignment conflict etc.) | I7 |
| 20 | Offline Banner | Persistent top banner when device has no connectivity, reassures employee that data is saved locally | I6 |

---

## 7. Profile & Settings

| # | Screen | Purpose | Feature Refs |
|---|---|---|---|
| 21 | My Profile | Employee's own details (read-only for MVP — editing is admin-only per B1) | A7 |
| 22 | App Settings | Logout, notification preferences (if any), app version info | L3 |

---

## Screen Count Summary

| Flow Area | Screen Count |
|---|---|
| Auth | 2 |
| Dashboard/Home | 3 |
| Visit | 5 |
| Requirement Capture | 3 |
| Signature & Completion | 4 |
| Sync & Offline | 3 |
| Profile & Settings | 2 |
| **Total** | **22** |

Note: several "screens" above (Navigation Handoff, Pending Sync Badge, Offline Banner) are states/components rather than full-screen destinations — listed anyway because they need explicit design attention, just not separate wireframe canvases.

---

**Next up:** Admin Dashboard Screen List — same exercise for the web dashboard side, before moving into actual wireframe layouts.
