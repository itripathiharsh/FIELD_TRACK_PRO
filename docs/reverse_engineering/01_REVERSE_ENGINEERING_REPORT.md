# FieldTrack Pro — Reverse Engineering Report

**Date:** 2026-08-19
**Commit:** `760a66379658727b3d3277413d62333b8523a022`

---

## PHASE 1 — Master Feature Inventory

See: `00_MASTER_FEATURE_CHECKLIST.md`

**Summary:**
- ✅ IMPLEMENTED: 52
- 🟡 PARTIAL: 12
- 🟠 NOT REACHABLE: 2
- 🔴 MISSING: 37
- **Total: 103 features**

---

## PHASE 2 — Dependency Graph

### Critical Dependency Chains

```
Customer Map (Web)
├── Customer coordinates (DB) ✅
├── Backend customer API ✅
├── Frontend API client ✅
├── MapPage ✅
├── FieldTrackMap component ✅
├── tileConfig ✅
└── Sidebar navigation ✅ (FIXED)

Visit Detail Map (Android)
├── Customer coordinates (DB) ✅
├── Backend customer API ✅
├── Retrofit API client ✅
├── MapScreen component ✅
├── Screen.Map sealed class ✅ (FIXED)
├── NavGraph route ✅ (FIXED)
└── VisitDetailsScreen preview ✅ (FIXED)

Android Check-In Flow
├── Visit exists ✅
├── Customer coordinates ✅
├── GPS permission ✅
├── LocationManager capture ✅
├── Coordinate validation ✅
├── POST check-in API ✅
├── Visit state transition ✅
├── Audit log ✅
└── UI state update ✅

Reports Module (MISSING)
├── Backend report endpoints 🔴
├── Frontend report pages 🔴
├── Report data aggregation 🔴
├── Date-range filtering 🔴
└── Export functionality 🔴

Requirement Form (MISSING)
├── Form renderer component 🔴
├── Category management 🔴
├── Local auto-save 🔴
└── Form submission API 🔴

Notifications Module (MISSING)
├── FCM integration 🔴
├── Push delivery 🔴
├── Notification UI 🔴
└── Notification preferences 🔴
```

---

## PHASE 3 — Web Audit

### Route Inventory

| Route | Page | Auth | Role | Status |
|-------|------|------|------|--------|
| / | DashboardPage | YES | All | ✅ |
| /login | LoginPage | NO | - | ✅ |
| /employees | EmployeesPage | YES | ADMIN | ✅ |
| /territories | TerritoriesPage | YES | ADMIN | ✅ |
| /customers | CustomersPage | YES | ADMIN | ✅ |
| /visits | VisitsPage | YES | All | ✅ |
| /visits/:id | VisitDetailsPage | YES | All | ✅ |
| /geo-logs | GeoLogsPage | YES | ADMIN | ✅ |
| /media | MediaViewerPage | YES | ADMIN | ✅ |
| /map | MapPage | YES | ADMIN | ✅ (FIXED) |
| /forms | FormsPage | YES | All | ✅ (honest state) |
| /reports | ReportsPage | YES | ADMIN | ✅ (honest state) |
| /settings | SettingsPage | YES | ADMIN | ✅ |
| /profile | ProfilePage | YES | All | ✅ |

### Sidebar Navigation

| Item | Path | Roles | Status |
|------|------|-------|--------|
| Dashboard | / | All | ✅ |
| Employees | /employees | ADMIN | ✅ |
| Territories | /territories | ADMIN | ✅ |
| Customers | /customers | ADMIN | ✅ |
| Visits | /visits | All | ✅ |
| **Map** | **/map** | **ADMIN** | **✅ (FIXED)** |
| Geo Logs | /geo-logs | ADMIN | ✅ |
| Media Vault | /media | ADMIN | ✅ |
| Forms | /forms | All | ✅ |
| Reports | /reports | ADMIN | ✅ |

### Web Defects Found

| ID | Severity | Description |
|----|----------|-------------|
| W1 | MEDIUM | Employee Detail page (W7) not implemented |
| W2 | MEDIUM | Customer Detail page (W11) not implemented |
| W3 | HIGH | Reports module not functional (shows honest "not available" state) |
| W4 | HIGH | Export modal not implemented |
| W5 | MEDIUM | Flagged Visit Review page not implemented |
| W6 | MEDIUM | Bulk Schedule Visits not implemented |
| W7 | MEDIUM | Requirement Category Management not implemented |

---

## PHASE 4 — Android Audit

### Screen Inventory

| Screen | Route | NavGraph | Status |
|--------|-------|----------|--------|
| Splash | splash | ✅ | ✅ |
| Login | login | ✅ | ✅ |
| Dashboard | dashboard | ✅ | ✅ |
| TodayVisits | today_visits | ✅ | ✅ |
| VisitDetails | visit_details/{visitId} | ✅ | ✅ |
| CheckIn | check_in/{visitId}/{customerId} | ✅ | ✅ |
| CheckOut | check_out/{visitId}/{customerId} | ✅ | ✅ |
| MediaUpload | media_upload/{visitId} | ✅ | ✅ |
| Map | map/{customerId} | ✅ (FIXED) | ✅ (FIXED) |
| ProfileSettings | profile_settings | ✅ | ✅ |
| OfflineQueue | offline_queue | ✅ | ✅ |

### Android Defects Found

| ID | Severity | Description | Screen List Ref |
|----|----------|-------------|-----------------|
| A1 | HIGH | Notifications List screen not implemented | #5 |
| A2 | HIGH | Requirement Form not implemented | #11 |
| A3 | MEDIUM | Attachment Preview not implemented | #13 |
| A4 | HIGH | Visit Summary/Review not implemented | #16 |
| A5 | MEDIUM | Submission Success State not implemented | #17 |
| A6 | MEDIUM | Geo-fence Waiting State not implemented | #8 |
| A7 | MEDIUM | Check-in Confirmation Dialog not implemented | #9 |
| A8 | LOW | Sync Conflict Notice not implemented | #19 |
| A9 | LOW | Pull-to-refresh not implemented | I4 |
| A10 | LOW | Pending Sync Badge incomplete | I8 |

---

## PHASE 5 — Backend/API Audit

### Complete Route Inventory

| Method | Path | Auth | Role | Frontend | Android | Status |
|--------|------|------|------|----------|---------|--------|
| POST | /api/v1/auth/login | NO | - | ✅ | ✅ | ✅ |
| POST | /api/v1/auth/logout | YES | - | ✅ | ✅ | ✅ |
| GET | /api/v1/auth/me | YES | - | ✅ | ✅ | ✅ |
| POST | /api/v1/auth/refresh | NO | - | ✅ | ✅ | ✅ |
| PATCH | /api/v1/users/me/password | YES | - | ✅ | 🔴 | ✅ |
| GET | /api/v1/users | YES | ADMIN | ✅ | 🔴 | ✅ |
| POST | /api/v1/users | YES | ADMIN | ✅ | 🔴 | ✅ |
| GET | /api/v1/users/{id} | YES | - | 🔴 | 🔴 | 🟠 ORPHAN |
| PATCH | /api/v1/users/{id}/activate | YES | ADMIN | 🔴 | 🔴 | 🟠 ORPHAN |
| PATCH | /api/v1/users/{id}/deactivate | YES | ADMIN | 🔴 | 🔴 | 🟠 ORPHAN |
| GET | /api/v1/customers | YES | - | ✅ | ✅ | ✅ |
| POST | /api/v1/customers | YES | ADMIN | ✅ | 🔴 | ✅ |
| GET | /api/v1/customers/{id} | YES | - | ✅ | ✅ | ✅ |
| PATCH | /api/v1/customers/{id} | YES | ADMIN | ✅ | 🔴 | ✅ |
| GET | /api/v1/visits | YES | - | ✅ | ✅ | ✅ |
| POST | /api/v1/visits | YES | ADMIN | ✅ | 🔴 | ✅ |
| GET | /api/v1/visits/me/today | YES | EMPLOYEE | 🔴 | ✅ | ✅ |
| GET | /api/v1/visits/{id} | YES | - | ✅ | ✅ | ✅ |
| POST | /api/v1/visits/{id}/check-in | YES | - | 🔴 | ✅ | ✅ |
| POST | /api/v1/visits/{id}/check-out | YES | - | 🔴 | ✅ | ✅ |
| GET | /api/v1/visits/{id}/geo-logs | YES | - | ✅ | ✅ | ✅ |
| GET | /api/v1/visits/{id}/media | YES | - | ✅ | ✅ | ✅ |
| POST | /api/v1/visits/{id}/media | YES | - | 🔴 | ✅ | ✅ |
| GET | /api/v1/visits/{id}/signatures | YES | - | 🔴 | ✅ | ✅ |
| POST | /api/v1/visits/{id}/signatures | YES | - | 🔴 | ✅ | ✅ |
| PATCH | /api/v1/visits/{id}/status | YES | ADMIN | 🔴 | 🔴 | 🟠 ORPHAN |
| GET | /api/v1/employees | YES | - | ✅ | 🔴 | ✅ |
| POST | /api/v1/employees | YES | ADMIN | ✅ | 🔴 | ✅ |
| GET | /api/v1/employees/me | YES | - | 🔴 | 🔴 | 🟠 ORPHAN |
| GET | /api/v1/employees/{id} | YES | - | 🔴 | 🔴 | 🟠 ORPHAN |
| GET | /api/v1/territories | YES | - | ✅ | 🔴 | ✅ |
| POST | /api/v1/territories | YES | ADMIN | ✅ | 🔴 | ✅ |
| GET | /api/v1/territories/{id} | YES | - | 🔴 | 🔴 | 🟠 ORPHAN |
| DELETE | /api/v1/territories/{id} | YES | ADMIN | ✅ | 🔴 | ✅ |
| PATCH | /api/v1/territories/{id} | YES | ADMIN | ✅ | 🔴 | ✅ |
| POST | /api/v1/geo/verify-location | YES | - | ✅ | ✅ | ✅ |
| GET | /api/v1/media/{id} | YES | - | 🔴 | 🔴 | 🟠 ORPHAN |
| GET | /api/v1/media/{id}/download | YES | - | 🔴 | 🔴 | 🟠 ORPHAN |
| DELETE | /api/v1/media/{id} | YES | - | 🔴 | 🔴 | 🟠 ORPHAN |
| GET | /api/v1/signatures/{id}/download | YES | - | 🔴 | 🔴 | 🟠 ORPHAN |

### Orphan Endpoints (Backend exists, no UI)

| Endpoint | Reason |
|----------|--------|
| GET /api/v1/users/{id} | No user detail page |
| PATCH /api/v1/users/{id}/activate | No user management UI action |
| PATCH /api/v1/users/{id}/deactivate | No user management UI action |
| GET /api/v1/employees/me | No Android employee detail |
| GET /api/v1/employees/{id} | No employee detail page |
| GET /api/v1/territories/{id} | No territory detail page |
| PATCH /api/v1/visits/{id}/status | No admin status override UI |
| GET /api/v1/media/{id} | No media detail page |
| GET /api/v1/media/{id}/download | No media download UI |
| DELETE /api/v1/media/{id} | No media delete UI |
| GET /api/v1/signatures/{id}/download | No signature download UI |

---

## PHASE 6 — Database Audit

### Table Inventory

| Table | Columns | Used | Status |
|-------|---------|------|--------|
| users | 8 | ✅ | ✅ |
| employees | 6 | ✅ | ✅ |
| customers | 9 | ✅ | ✅ |
| territories | 3 | ✅ | ✅ |
| visits | 12 | ✅ | ✅ |
| visit_media | 8 | ✅ | ✅ |
| visit_signatures | 4 | ✅ | ✅ |
| geo_verification_logs | 8 | ✅ | ✅ |
| refresh_tokens | 5 | ✅ | ✅ |

### Database Features Not Fully Used

| Feature | Status | Notes |
|---------|--------|-------|
| visit_media.checksum_sha256 | ✅ Used | Duplicate detection |
| geo_verification_logs immutability | ✅ Used | INSERT only |
| PostGIS spatial indexes | ✅ Used | GIST indexes |
| visits.synced field | 🟡 Partial | Offline sync indicator |

---

## PHASE 7 — Media Audit

### Media Pipeline

| Step | Backend | Web | Android | Status |
|------|---------|-----|---------|--------|
| Upload | ✅ | 🔴 | ✅ | 🟡 |
| Validation | ✅ | 🔴 | ✅ | 🟡 |
| Compression | ✅ | 🔴 | ✅ | 🟡 |
| Storage | ✅ | 🔴 | ✅ | 🟡 |
| DB Record | ✅ | 🔴 | ✅ | 🟡 |
| Pre-signed URL | ✅ | 🔴 | 🔴 | 🟡 |
| Download | ✅ | 🔴 | 🔴 | 🟡 |
| Delete | ✅ | 🔴 | 🔴 | 🟡 |

### Signature Pipeline

| Step | Backend | Android | Status |
|------|---------|---------|--------|
| Capture | - | ✅ | ✅ |
| Validation | ✅ | ✅ | ✅ |
| Storage | ✅ | ✅ | ✅ |
| DB Record | ✅ | ✅ | ✅ |
| Download | ✅ | 🔴 | 🟡 |

---

## PHASE 8 — Security Audit

### Security Controls

| Control | Status | Notes |
|---------|--------|-------|
| JWT authentication | ✅ | bcrypt cost 12 |
| Role-based access | ✅ | ADMIN/EMPLOYEE |
| Ownership checks | ✅ | get_visit_for_user |
| Rate limiting | ✅ | 5/15min login |
| CORS | ✅ | Configured |
| Audit immutability | ✅ | DB-level |
| Input validation | ✅ | Pydantic schemas |
| Phone validation | ✅ | NEW (this repair) |
| SQL injection | ✅ | Parameterized |
| Path traversal | ✅ | Filename sanitization |
| Pre-signed URLs | ✅ | 15-min expiry |

---

## PHASE 9 — State Machine Audit

### Visit State Machine

| From | To | Trigger | UI | Status |
|------|----|---------|----|--------|
| PENDING | IN_PROGRESS | Check-in | ✅ | ✅ |
| IN_PROGRESS | COMPLETED | Check-out | ✅ | ✅ |
| PENDING | MISSED | Scheduler | ✅ | ✅ |
| PENDING | FLAGGED | Geo-fail ×3 | ✅ | ✅ |
| FLAGGED | IN_PROGRESS | Check-in | ✅ | ✅ |
| FLAGGED | COMPLETED | Check-out | ✅ | ✅ |
| COMPLETED | - | Terminal | ✅ | ✅ |
| MISSED | - | Terminal | ✅ | ✅ |

**State machine is correctly implemented.**

---

## PHASE 10 — Test Coverage Audit

### Coverage Summary

| Module | Features | Tested | Coverage |
|--------|----------|--------|----------|
| Auth | 11 | 15 | ✅ HIGH |
| Customers | 6 | 8 | ✅ HIGH |
| Visits | 11 | 20 | ✅ HIGH |
| Media | 10 | 25 | ✅ HIGH |
| Geofencing | 7 | 11 | ✅ HIGH |
| Maps | 6 | 0 | 🔴 NONE |
| Reports | 6 | 0 | 🔴 NONE |
| Forms | 4 | 0 | 🔴 NONE |
| Notifications | 4 | 0 | 🔴 NONE |

---

## PHASE 11 — Missing/Disconnected Features

### Critical Missing Features (No Implementation)

| ID | Feature | Module | Severity |
|----|---------|--------|----------|
| M1 | Reports Module (all) | K | HIGH |
| M2 | Requirement Form | H | HIGH |
| M3 | Notifications (FCM) | L | HIGH |
| M4 | Employee Detail page | B | MEDIUM |
| M5 | Customer Detail page | C | MEDIUM |
| M6 | Flagged Visit Review | K | MEDIUM |
| M7 | Bulk Schedule Visits | D | MEDIUM |
| M8 | Export functionality | K | MEDIUM |
| M9 | Android Notifications List | L | MEDIUM |
| M10 | Android Attachment Preview | G | MEDIUM |
| M11 | Android Visit Summary/Review | I | MEDIUM |
| M12 | Auto-geocode address | C | LOW |

### Disconnected Features (Exist but Unreachable)

| ID | Feature | Issue |
|----|---------|-------|
| D1 | Web MapPage | Fixed — Sidebar entry added |
| D2 | Android MapScreen | Fixed — NavGraph wired |
| D3 | Android Map Preview | Fixed — VisitDetailsScreen updated |

---

## PHASE 12 — Confirmed Defects

| ID | Severity | Component | Description |
|----|----------|-----------|-------------|
| 1 | HIGH | Web | Reports module completely missing |
| 2 | HIGH | Web | Employee Detail page missing |
| 3 | HIGH | Web | Customer Detail page missing |
| 4 | HIGH | Android | Requirement Form missing |
| 5 | HIGH | Android | Notifications List missing |
| 6 | HIGH | Android | Attachment Preview missing |
| 7 | HIGH | Android | Visit Summary/Review missing |
| 8 | MEDIUM | Web | Flagged Visit Review page missing |
| 9 | MEDIUM | Web | Export modal missing |
| 10 | MEDIUM | Web | Bulk Schedule missing |
| 11 | MEDIUM | Web | Requirement Category Management missing |
| 12 | MEDIUM | Android | Geo-fence Waiting State missing |
| 13 | MEDIUM | Android | Check-in Confirmation Dialog missing |
| 14 | MEDIUM | Backend | Multiple orphan endpoints |

---

## PHASE 13 — Ambiguities

| ID | Question | Impact |
|----|----------|--------|
| 1 | Should reports be real-time or batch? | Report design |
| 2 | Should Android offline use Room or just queue? | Offline architecture |
| 3 | What notification types are MVP? | FCM integration |

---

## PHASE 14 — Deferred/Blocked Items

| ID | Item | Reason |
|----|------|--------|
| 1 | Map visual rendering verification | Requires browser/device |
| 2 | GPS capture verification | Requires physical device |
| 3 | Camera capture verification | Requires physical device |
| 4 | FCM push delivery | Requires Firebase project |

---

## PHASE 15 — Final Completeness Matrix

| Category | ✅ | 🟡 | 🟠 | 🔴 | Total |
|----------|----|----|----|----|-------|
| Web | 16 | 4 | 0 | 7 | 27 |
| Android | 14 | 4 | 0 | 9 | 27 |
| Backend | 30 | 4 | 10 | 0 | 44 |
| **Total** | **60** | **12** | **10** | **16** | **98** |

---

## TOP 20 Most Important Gaps (Ranked by Severity)

| Rank | Gap | Severity | Effort |
|------|-----|----------|--------|
| 1 | Reports Module (all 6 reports) | HIGH | Large |
| 2 | Requirement Form (Android) | HIGH | Large |
| 3 | Employee Detail page (Web) | MEDIUM | Small |
| 4 | Customer Detail page (Web) | MEDIUM | Small |
| 5 | Android Attachment Preview | MEDIUM | Small |
| 6 | Android Visit Summary/Review | MEDIUM | Medium |
| 7 | Flagged Visit Review (Web) | MEDIUM | Small |
| 8 | Export functionality | MEDIUM | Medium |
| 9 | FCM Notifications | HIGH | Large |
| 10 | Bulk Schedule Visits | MEDIUM | Medium |
| 11 | Requirement Category Management | MEDIUM | Small |
| 12 | Android Notifications List | MEDIUM | Small |
| 13 | Geo-fence Waiting State | MEDIUM | Small |
| 14 | Check-in Confirmation Dialog | MEDIUM | Small |
| 15 | Auto-geocode address | LOW | Medium |
| 16 | Map marker clustering | LOW | Small |
| 17 | Sync Conflict Notice | LOW | Small |
| 18 | Pull-to-refresh | LOW | Small |
| 19 | Employee employee_id on Visit API | LOW | Small |
| 20 | Orphan endpoint cleanup | LOW | Small |

---

## FINAL VERDICT

**STATUS: INCOMPLETE**

The application has a solid core (auth, visits, check-in/out, media, geofencing) but is missing entire modules (Reports, Requirement Forms, Notifications) and several key screens.

**Completeness: ~60%** of specified MVP features are implemented and reachable.
