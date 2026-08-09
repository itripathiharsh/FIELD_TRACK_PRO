# Phase 6 — Maps, Geospatial Operations & Navigation
# Requirement Reconciliation

**Date:** 2026-08-09
**Source of truth:** Original planning documents

---

## 1. Source Documents Audited

| Document | Path | Key Sections |
|----------|------|--------------|
| Tech Stack | `guides/04_tech_stack.md` | Google Maps SDK, Fused Location |
| Architecture | `guides/05_architecture.md` | Service layer design |
| Database Design | `guides/06_database_design.md` | PostGIS, spatial types |
| API Design | `guides/07_api_design.md` | Geo endpoints |
| Security Design | `guides/09_security_design.md` | Mock detection, authority |
| Business Logic | `guides/19_business_logic.md` | Geofencing, check-in flow |
| Maps & Location | `guides/phase4/21_maps_location_services.md` | Full Phase 4 spec |
| Android App | `guides/phase6/23_android_application.md` | Android implementation |
| Android Screens | `guides/Phase 2.5/11_android_screen_list.md` | Screen inventory |
| User Journey | `guides/Phase 2.5/13_user_journey.md` | Navigation flows |

---

## 2. Requirement Inventory

### Backend Geospatial

| ID | Requirement | Source | Priority |
|----|-------------|--------|----------|
| B1 | PostGIS Geography POINT SRID 4326 | 06_database_design, 21_maps S3 | CRITICAL |
| B2 | ST_DWithin for geofence check | 19_business_logic, 21_maps S3 | CRITICAL |
| B3 | ST_Distance returns meters | 19_business_logic, 21_maps S5A | CRITICAL |
| B4 | Correct lng/lat ordering in WKT | 06_database_design | CRITICAL |
| B5 | Spatial indexes (GIST) | 06_database_design | HIGH |
| B6 | Coordinate validation (range check) | 09_security S5 | CRITICAL |
| B7 | Mock location detection | 09_security S7, 21_maps S2 | CRITICAL |
| B8 | GPS accuracy threshold | 09_security S7 | HIGH |
| B9 | No (0,0) fallback | REPAIR_DECISIONS RD-004 | CRITICAL |
| B10 | Daily distance traveled calculation | 21_maps S5B | MEDIUM |
| B11 | Audit log for geo-verification | 19_business_logic | CRITICAL |

### Web Map Experience

| ID | Requirement | Source | Priority |
|----|-------------|--------|----------|
| W1 | Google Maps JavaScript API | 21_maps S1 | HIGH |
| W2 | Customer location display on map | 21_maps S1 | HIGH |
| W3 | Coordinate editing with persistence | 13_user_journey | HIGH |
| W4 | Geofence radius visualization | 21_maps S3 | MEDIUM |
| W5 | Real browser Geolocation API | 13_user_journey | HIGH |
| W6 | No hardcoded/fake coordinates | REPAIR_DECISIONS | CRITICAL |
| W7 | Loading/error/empty states | 30_definition_of_done | MEDIUM |
| W8 | Admin map overview (employee locations) | 21_maps S2 | MEDIUM |

### Android Map & Navigation

| ID | Requirement | Source | Priority |
|----|-------------|--------|----------|
| A1 | Google Maps SDK (maps-compose) | 21_maps S1, 23_android S4 | HIGH |
| A2 | Fused Location Provider | 21_maps S2, 23_android S4 | CRITICAL |
| A3 | Event-based location (check-in/out) | 21_maps S2 | CRITICAL |
| A4 | Geofencing API (arrival trigger) | 21_maps S3 | MEDIUM |
| A5 | Navigation deep-link to Google Maps | 21_maps S4 | HIGH |
| A6 | Navigation fallback (geo: URI) | 21_maps S4 | HIGH |
| A7 | Map marker for customer location | 23_android S4 | HIGH |
| A8 | No (0,0) fallback for missing coords | REPAIR_DECISIONS | CRITICAL |
| A9 | Location permission handling | 21_maps S1 | CRITICAL |
| A10 | GPS disabled/unavailable states | 23_android S4 | HIGH |

---

## 3. Current Implementation Status

### Backend (VERIFIED)

| ID | Status | Evidence |
|----|--------|----------|
| B1 | **VERIFIED** | `customer_service.py:172-180` uses `ST_Distance(Customer.location, ST_GeogFromText(device_wkt))` on geography |
| B2 | **VERIFIED** | `geo_verification_service.py` uses `measured_distance_m` from PostGIS |
| B3 | **VERIFIED** | PostGIS `ST_Distance` on geography returns meters |
| B4 | **VERIFIED** | `visit_service.py:198` uses `POINT({lng} {lat})` - correct WKT order |
| B5 | **VERIFIED** | `idx_customers_location` GIST index in migration |
| B6 | **VERIFIED** | `geo_verification_service.py:95-103` validates lat/lng ranges |
| B7 | **VERIFIED** | `geo_verification_service.py:106-114` detects mock locations |
| B8 | **VERIFIED** | `geo_verification_service.py:117-128` enforces 100m accuracy threshold |
| B9 | **VERIFIED** | No (0,0) fallback found in code |
| B10 | **MISSING** | No daily distance calculation service |
| B11 | **VERIFIED** | `geo_verification_logs` table with audit trail |

### Web (PARTIAL)

| ID | Status | Evidence |
|----|--------|----------|
| W1 | **MISSING** | No Google Maps JS API integration found |
| W2 | **MISSING** | No map display in CustomersPage or VisitDetailsPage |
| W3 | **VERIFIED** | `CustomersPage.tsx:88-115` coordinate input with validation |
| W4 | **MISSING** | No geofence visualization |
| W5 | **VERIFIED** | `VisitDetailsPage.tsx:73-85` uses `navigator.geolocation` |
| W6 | **VERIFIED** | No hardcoded coordinates found |
| W7 | **PARTIAL** | Some loading/error states present |
| W8 | **MISSING** | No admin map overview |

### Android (PARTIAL)

| ID | Status | Evidence |
|----|--------|----------|
| A1 | **MISSING** | No Google Maps SDK integration found |
| A2 | **MISSING** | No Fused Location Provider implementation |
| A3 | **PARTIAL** | CheckInScreen has coordinate text fields (manual entry) |
| A4 | **MISSING** | No Geofencing API implementation |
| A5 | **MISSING** | No navigation deep-link implementation |
| A6 | **MISSING** | No fallback navigation |
| A7 | **MISSING** | No map markers |
| A8 | **VERIFIED** | No (0,0) fallback found |
| A9 | **MISSING** | CAMERA permission only, no location permission handling |
| A10 | **MISSING** | No GPS state handling |

---

## 4. Critical Findings

### 4.1 Backend is Solid
The backend geospatial implementation is correct and follows the specification:
- PostGIS is the authority for distance calculations
- Correct WKT ordering (POINT(lng lat))
- Proper coordinate validation
- Mock location detection
- Audit logging

### 4.2 Web Needs Map Integration
The web has coordinate input/output but lacks:
- Google Maps display
- Visual map interaction
- Geofence radius visualization
- Admin overview map

### 4.3 Android Needs Complete Map/Navigation Layer
The Android app has the UI shell but lacks:
- Google Maps SDK integration
- Real GPS location capture
- Navigation to customer
- Location permission handling
- Geofencing triggers

### 4.4 Missing Distance Traveled Feature
Phase 4 Section 5B specifies a daily distance traveled calculation
for the Productivity Dashboard. This is not implemented.

---

## 5. Gaps Requiring Implementation

### Critical (Must Fix)
1. **A2: Fused Location Provider** - Android needs real GPS capture
2. **A5/A6: Navigation intent** - Deep-link to Google Maps for directions
3. **A9: Location permission** - Android needs runtime permission handling
4. **A1: Google Maps display** - Customer location on map

### High (Should Fix)
5. **W1/W2: Web Google Maps** - Customer location display
6. **W8: Admin map overview** - Employee last-known locations
7. **B10: Distance traveled** - Daily productivity metric
8. **A4: Geofencing API** - Arrival trigger for check-in

### Medium (Nice to Have)
9. **W4: Geofence visualization** - Radius circle on map
10. **A7: Map markers** - Custom markers for customers

---

## 6. API Contract Verification

### Existing Endpoints

| Endpoint | Method | Auth | Status |
|----------|--------|------|--------|
| `/api/v1/geo/verify-location` | POST | Yes | VERIFIED |
| `/api/v1/visits/{id}/check-in` | POST | Yes | VERIFIED |
| `/api/v1/visits/{id}/check-out` | POST | Yes | VERIFIED |
| `/api/v1/visits/{id}/geo-logs` | GET | Yes | VERIFIED |
| `/api/v1/customers/{id}` | GET | Yes | VERIFIED |

### Schema Verification

| Schema | Field | Expected | Actual | Match |
|--------|-------|----------|--------|-------|
| LocationVerifyRequest | latitude | float | float | YES |
| LocationVerifyRequest | longitude | float | float | YES |
| LocationVerifyRequest | accuracy_m | float? | float? | YES |
| LocationVerifyRequest | is_mock_location | bool | bool | YES |
| LocationVerifyResponse | is_valid | bool | bool | YES |
| LocationVerifyResponse | distance_m | float | float | YES |
| LocationVerifyResponse | geofence_radius_m | float | float | YES |

---

## 7. Security Verification

| Control | Status | Evidence |
|---------|--------|----------|
| PostGIS authority | VERIFIED | `customer_service.py:172-180` |
| No (0,0) fallback | VERIFIED | Code inspection |
| Mock detection | VERIFIED | `geo_verification_service.py:106` |
| Coordinate validation | VERIFIED | `geo_verification_service.py:95` |
| Ownership checks | VERIFIED | `get_visit_for_user` used |
| Audit logging | VERIFIED | `geo_verification_logs` table |

---

## 8. Test Coverage

### Existing Tests

| Test File | Coverage |
|-----------|----------|
| `test_geo_verification.py` | Haversine, coordinate validation, mock detection |
| `test_geo_integration.py` | PostGIS distance, geofence boundary |
| `test_geo_audit_integration.py` | Audit log reading |

### Missing Tests

| Gap | Required Test |
|-----|---------------|
| Android GPS capture | Location permission flow |
| Navigation intent | URI construction |
| Web map rendering | Map component |
| Distance traveled | Calculation accuracy |

---

## 9. Recommended Implementation Priority

1. **Android Fused Location Provider** - Core GPS functionality
2. **Android Navigation Intent** - Deep-link to Google Maps
3. **Android Location Permissions** - Runtime permission handling
4. **Android Google Maps Display** - Customer location on map
5. **Web Google Maps Integration** - Customer/tenant map views
6. **Distance Traveled Calculation** - Backend service
7. **Geofencing API** - Android arrival trigger
8. **Admin Map Overview** - Employee locations

---

## 10. Out of Scope (This Phase)

| Item | Reason |
|------|--------|
| Live location tracking | Phase 4 S2: event-based only |
| In-app turn-by-turn navigation | Phase 4 S4: deep-link handoff |
| Territory polygon management | Not specified in planning |
| Continuous GPS polling | Phase 4 S2: event-based only |
