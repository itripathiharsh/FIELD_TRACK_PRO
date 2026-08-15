# FieldTrack Pro — Master Feature Checklist

**Date:** 2026-08-19
**Source:** All planning documents, phase specs, screen lists, API docs, database design

---

## Module A: Authentication & Access Control

| # | Feature | Spec Source | Status |
|---|---------|-------------|--------|
| A1 | Employee login (email/mobile + password) | 03_features.md | ✅ IMPLEMENTED |
| A2 | Admin login (separate flow) | 03_features.md | ✅ IMPLEMENTED |
| A3 | JWT access + refresh token issuance | 03_features.md | ✅ IMPLEMENTED |
| A4 | Password hashing (bcrypt) | 03_features.md | ✅ IMPLEMENTED |
| A5 | Role-based authorization middleware | 03_features.md | ✅ IMPLEMENTED |
| A6 | Login rate-limiting | 03_features.md | ✅ IMPLEMENTED |
| A7 | Secure token storage (EncryptedSharedPreferences) | 03_features.md | ✅ IMPLEMENTED |
| A8 | Token refresh endpoint | 03_features.md | ✅ IMPLEMENTED |
| A9 | Logout (server-side revocation) | 03_features.md | ✅ IMPLEMENTED |
| A10 | Password change (min length 8) | 03_features.md | ✅ IMPLEMENTED |
| A11 | Inactive user cannot login | 03_features.md | ✅ IMPLEMENTED |

---

## Module B: Employee Management

| # | Feature | Spec Source | Status |
|---|---------|-------------|--------|
| B1 | Create/edit/deactivate employee (backend) | 03_features.md | ✅ IMPLEMENTED |
| B2 | Assign employee to territory | 03_features.md | ✅ IMPLEMENTED |
| B3 | Admin UI: employee list with search/filter | 03_features.md | ✅ IMPLEMENTED |
| B4 | Admin UI: add/edit employee form | 03_features.md | ✅ IMPLEMENTED |
| B5 | Employee detail page with visit history | 12_web_dashboard.md | 🔴 MISSING |

---

## Module C: Customer Management

| # | Feature | Spec Source | Status |
|---|---------|-------------|--------|
| C1 | Create/edit customer record (backend) | 03_features.md | ✅ IMPLEMENTED |
| C2 | Auto-geocode customer address → lat/long | 03_features.md | 🔴 MISSING |
| C3 | Configurable geofence radius per customer | 03_features.md | ✅ IMPLEMENTED |
| C4 | Admin UI: customer list with search/filter | 03_features.md | ✅ IMPLEMENTED |
| C5 | Admin UI: add/edit customer form | 03_features.md | ✅ IMPLEMENTED |
| C6 | Customer detail page with visit history | 03_features.md | 🔴 MISSING |

---

## Module D: Visit Scheduling & Assignment

| # | Feature | Spec Source | Status |
|---|---------|-------------|--------|
| D1 | Create visit (customer + employee + datetime) | 03_features.md | ✅ IMPLEMENTED |
| D2 | Bulk/recurring visit assignment | 03_features.md | 🔴 MISSING |
| D3 | Visit status state machine | 03_features.md | ✅ IMPLEMENTED |
| D4 | Admin UI: visit scheduling form | 03_features.md | 🟡 PARTIAL |
| D5 | Admin UI: real-time visit status board (Kanban) | 03_features.md | 🟡 PARTIAL |

---

## Module E: GPS & Geofencing

| # | Feature | Spec Source | Status |
|---|---------|-------------|--------|
| E1 | Geofence radius check service (backend) | 03_features.md | ✅ IMPLEMENTED |
| E2 | Distance calculation (PostGIS) | 03_features.md | ✅ IMPLEMENTED |
| E3 | Android: GPS capture at check-in/out | 03_features.md | ✅ IMPLEMENTED |
| E4 | Android: auto-trigger check-in prompt on geofence entry | 03_features.md | 🔴 MISSING |
| E5 | Check-in verification endpoint (server-side) | 03_features.md | ✅ IMPLEMENTED |
| E6 | Failed-verification handling + retry flow | 03_features.md | ✅ IMPLEMENTED |
| E7 | Geo-verification flagging logic | 03_features.md | ✅ IMPLEMENTED |

---

## Module F: Maps & Navigation

| # | Feature | Spec Source | Status |
|---|---------|-------------|--------|
| F1 | MapLibre SDK integration (Android) | 03_features.md | ✅ IMPLEMENTED |
| F2 | "Navigate to customer" deep link | 03_features.md | ✅ IMPLEMENTED |
| F3 | Admin dashboard live map | 03_features.md | 🟠 NOT REACHABLE |
| F4 | Map marker clustering for admin view | 03_features.md | 🔴 MISSING |
| F5 | Web: Customer Locations Map page | 12_web_dashboard.md | 🟠 NOT REACHABLE |
| F6 | Android: Map preview on Visit Detail | 11_android_screen_list.md | 🟡 PARTIAL |

---

## Module G: File & Media Management

| # | Feature | Spec Source | Status |
|---|---------|-------------|--------|
| G1 | Image upload endpoint + storage | 03_features.md | ✅ IMPLEMENTED |
| G2 | Document upload endpoint + storage | 03_features.md | ✅ IMPLEMENTED |
| G3 | Digital signature capture (Android canvas) | 03_features.md | ✅ IMPLEMENTED |
| G4 | Signature storage linked to visit | 03_features.md | ✅ IMPLEMENTED |
| G5 | File size/type validation + compression | 03_features.md | ✅ IMPLEMENTED |
| G6 | Pre-signed URL download | 03_features.md | ✅ IMPLEMENTED |
| G7 | Duplicate detection (checksum) | 03_features.md | ✅ IMPLEMENTED |
| G8 | Android: Camera capture | 03_features.md | ✅ IMPLEMENTED |
| G9 | Android: File picker | 03_features.md | ✅ IMPLEMENTED |
| G10 | Media preview/download on Android | 03_features.md | 🔴 MISSING |

---

## Module H: Requirement Capture Form

| # | Feature | Spec Source | Status |
|---|---------|-------------|--------|
| H1 | Dynamic form renderer (Android) | 03_features.md | 🔴 MISSING |
| H2 | Requirement category dropdown | 03_features.md | 🔴 MISSING |
| H3 | Local auto-save while filling form | 03_features.md | 🔴 MISSING |
| H4 | Form submission → linked to visit | 03_features.md | 🔴 MISSING |

---

## Module I: Android Core App

| # | Feature | Spec Source | Status |
|---|---------|-------------|--------|
| I1 | Splash + login screens | 03_features.md | ✅ IMPLEMENTED |
| I2 | Today's Visits dashboard | 03_features.md | ✅ IMPLEMENTED |
| I3 | Visit Detail screen | 03_features.md | ✅ IMPLEMENTED |
| I4 | Pull-to-refresh sync | 03_features.md | 🔴 MISSING |
| I5 | Push notification handling | 03_features.md | 🔴 MISSING |
| I6 | Offline local DB (Room/SQLite) | 03_features.md | 🟡 PARTIAL (queue only) |
| I7 | Background sync job | 03_features.md | 🟡 PARTIAL (WorkManager) |
| I8 | "Pending Sync" UI badge | 03_features.md | 🟡 PARTIAL |

---

## Module J: Admin Web Dashboard Core

| # | Feature | Spec Source | Status |
|---|---------|-------------|--------|
| J1 | Overview dashboard (summary cards) | 03_features.md | 🟡 PARTIAL |
| J2 | Navigation shell / layout | 03_features.md | ✅ IMPLEMENTED |
| J3 | Role-based UI gating | 03_features.md | ✅ IMPLEMENTED |

---

## Module K: Reports & Analytics

| # | Feature | Spec Source | Status |
|---|---------|-------------|--------|
| K1 | Employee Visit Report | 03_features.md | 🔴 MISSING |
| K2 | Customer Visit History report | 03_features.md | 🔴 MISSING |
| K3 | Productivity Dashboard | 03_features.md | 🔴 MISSING |
| K4 | Geo-verification Report | 03_features.md | 🔴 MISSING |
| K5 | Date-range filtering | 03_features.md | 🔴 MISSING |
| K6 | CSV/PDF export | 03_features.md | 🔴 MISSING |

---

## Module L: Notifications

| # | Feature | Spec Source | Status |
|---|---------|-------------|--------|
| L1 | Notification service (backend) | 03_features.md | 🟡 PARTIAL |
| L2 | Push notification delivery (FCM) | 03_features.md | 🔴 MISSING |
| L3 | Notification types (new visit, reminder, overdue) | 03_features.md | 🔴 MISSING |
| L4 | Admin alert on repeated geo-verification failures | 03_features.md | 🟡 PARTIAL |

---

## Additional Web Screens (from 12_web_dashboard.md)

| # | Screen | Spec Source | Status |
|---|--------|-------------|--------|
| W1 | Admin Login | 12_web_dashboard.md | ✅ IMPLEMENTED |
| W2 | Dashboard Overview | 12_web_dashboard.md | 🟡 PARTIAL |
| W3 | Live Map (full view) | 12_web_dashboard.md | 🟠 NOT REACHABLE |
| W4 | Employee List | 12_web_dashboard.md | ✅ IMPLEMENTED |
| W5 | Add Employee | 12_web_dashboard.md | ✅ IMPLEMENTED |
| W6 | Edit Employee | 12_web_dashboard.md | ✅ IMPLEMENTED |
| W7 | Employee Detail | 12_web_dashboard.md | 🔴 MISSING |
| W8 | Customer List | 12_web_dashboard.md | ✅ IMPLEMENTED |
| W9 | Add Customer | 12_web_dashboard.md | ✅ IMPLEMENTED |
| W10 | Edit Customer | 12_web_dashboard.md | ✅ IMPLEMENTED |
| W11 | Customer Detail | 12_web_dashboard.md | 🔴 MISSING |
| W12 | Visit List / Status Board | 12_web_dashboard.md | 🟡 PARTIAL |
| W13 | Schedule Visit | 12_web_dashboard.md | 🟡 PARTIAL |
| W14 | Bulk Schedule Visits | 12_web_dashboard.md | 🔴 MISSING |
| W15 | Visit Detail (Admin) | 12_web_dashboard.md | 🟡 PARTIAL |
| W16 | Flagged Visit Review | 12_web_dashboard.md | 🔴 MISSING |
| W17 | Employee Visit Report | 12_web_dashboard.md | 🔴 MISSING |
| W18 | Customer Visit History Report | 12_web_dashboard.md | 🔴 MISSING |
| W19 | Productivity Dashboard | 12_web_dashboard.md | 🔴 MISSING |
| W20 | Geo-verification Report | 12_web_dashboard.md | 🔴 MISSING |
| W21 | Export Modal | 12_web_dashboard.md | 🔴 MISSING |
| W22 | Territory Management | 12_web_dashboard.md | ✅ IMPLEMENTED |
| W23 | Requirement Category Management | 12_web_dashboard.md | 🔴 MISSING |
| W24 | Admin Settings | 12_web_dashboard.md | ✅ IMPLEMENTED |

---

## Additional Android Screens (from 11_android_screen_list.md)

| # | Screen | Spec Source | Status |
|---|--------|-------------|--------|
| A1 | Splash Screen | 11_android_screen_list.md | ✅ IMPLEMENTED |
| A2 | Login Screen | 11_android_screen_list.md | ✅ IMPLEMENTED |
| A3 | Today's Visits Dashboard | 11_android_screen_list.md | ✅ IMPLEMENTED |
| A4 | Empty State — No Visits | 11_android_screen_list.md | ✅ IMPLEMENTED |
| A5 | Notifications List | 11_android_screen_list.md | 🔴 MISSING |
| A6 | Visit Detail | 11_android_screen_list.md | ✅ IMPLEMENTED |
| A7 | Navigation Handoff | 11_android_screen_list.md | ✅ IMPLEMENTED |
| A8 | Geo-fence Waiting State | 11_android_screen_list.md | 🔴 MISSING |
| A9 | Check-in Confirmation Dialog | 11_android_screen_list.md | 🔴 MISSING |
| A10 | Check-in Failed/Retry State | 11_android_screen_list.md | 🟡 PARTIAL |
| A11 | Requirement Form | 11_android_screen_list.md | 🔴 MISSING |
| A12 | Photo/Document Attachment Picker | 11_android_screen_list.md | ✅ IMPLEMENTED |
| A13 | Attachment Preview | 11_android_screen_list.md | 🔴 MISSING |
| A14 | Employee Signature Pad | 11_android_screen_list.md | ✅ IMPLEMENTED |
| A15 | Customer Signature Pad | 11_android_screen_list.md | ✅ IMPLEMENTED |
| A16 | Visit Summary/Review | 11_android_screen_list.md | 🔴 MISSING |
| A17 | Submission Success State | 11_android_screen_list.md | 🔴 MISSING |
| A18 | Pending Sync Badge | 11_android_screen_list.md | 🟡 PARTIAL |
| A19 | Sync Conflict Notice | 11_android_screen_list.md | 🔴 MISSING |
| A20 | Offline Banner | 11_android_screen_list.md | 🟡 PARTIAL |
| A21 | My Profile | 11_android_screen_list.md | ✅ IMPLEMENTED |
| A22 | App Settings | 11_android_screen_list.md | ✅ IMPLEMENTED |

---

## Summary Counts

| Category | Count |
|----------|-------|
| ✅ IMPLEMENTED | 52 |
| 🟡 PARTIALLY IMPLEMENTED | 12 |
| 🟠 NOT REACHABLE | 2 |
| 🔴 MISSING | 37 |
| **Total** | **103** |
