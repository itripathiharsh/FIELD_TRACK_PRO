# Phase 6 — Maps, Geospatial Operations & Navigation
# Implementation Plan

**Date:** 2026-08-09
**Based on:** 01_REQUIREMENT_RECONCILIATION.md

---

## 1. Implementation Priority

### Tier 1 — Critical (Must Implement)

| ID | Requirement | Files | Tests |
|----|-------------|-------|-------|
| A2 | Fused Location Provider | `services/LocationCaptureService.kt` | Location capture test |
| A5/A6 | Navigation intent + fallback | `utils/NavigationHelper.kt` | URI construction test |
| A9 | Location permission handling | `MediaUploadScreen.kt` update | Permission state test |
| A1 | Google Maps display | `ui/screens/MapScreen.kt` | Map render test |

### Tier 2 — High (Should Implement)

| ID | Requirement | Files | Tests |
|----|-------------|-------|-------|
| W1/W2 | Web Google Maps | `pages/MapPage.tsx` | Map component test |
| B10 | Distance traveled | `services/report_service.py` | Calculation test |
| W8 | Admin map overview | `pages/DashboardPage.tsx` update | Overview test |

### Tier 3 — Medium (Nice to Have)

| ID | Requirement | Files | Tests |
|----|-------------|-------|-------|
| A4 | Geofencing API | `services/GeofenceManager.kt` | Geofence test |
| W4 | Geofence visualization | Map components | Visual test |

---

## 2. Android Implementation Details

### 2.1 Fused Location Provider

**File:** `app/src/main/java/com/fieldtrackpro/android/services/LocationCaptureService.kt`

```kotlin
class LocationCaptureService @Inject constructor(
    private val fusedLocationClient: FusedLocationProviderClient
) {
    suspend fun getCurrentLocation(): LocationResult
}
```

**Dependencies needed:**
- `com.google.android.gms:play-services-location:21.3.0`

### 2.2 Navigation Helper

**File:** `app/src/main/java/com/fieldtrackpro/android/utils/NavigationHelper.kt`

```kotlin
fun navigateToCustomer(context: Context, lat: Double, lng: Double, label: String) {
    val uri = Uri.parse("google.navigation:q=$lat,$lng")
    // ... with fallback to geo: URI
}
```

### 2.3 Location Permissions

**Updates to:** `AndroidManifest.xml`
```xml
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
```

### 2.4 Google Maps Screen

**File:** `app/src/main/java/com/fieldtrackpro/android/ui/screens/MapScreen.kt`

Uses `maps-compose:6.2.1` for Compose integration.

---

## 3. Web Implementation Details

### 3.1 Google Maps Page

**File:** `app/src/main/java/com/fieldtrackpro/web/src/pages/MapPage.tsx`

Uses `@react-google-maps/api` for React integration.

### 3.2 Dependencies

```bash
npm install @react-google-maps/api
```

---

## 4. Backend Implementation Details

### 4.1 Distance Traveled Service

**File:** `app/services/report_service.py`

```python
async def calculate_daily_distance_traveled(db, employee_id, target_date) -> float | None
```

Uses PostGIS ST_Distance on check_in_location/check_out_location sequence.

---

## 5. API Contract Changes

### New Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| (none new) | — | Existing endpoints sufficient |

### Modified Endpoints

| Endpoint | Change |
|----------|--------|
| (none) | Existing geo endpoints are correct |

---

## 6. Test Plan

### Backend Tests

| Test | File | Coverage |
|------|------|----------|
| Distance traveled | `test_report_service.py` | Calculation accuracy |
| Coordinate edge cases | `test_geo_verification.py` | Boundary values |

### Android Tests

| Test | File | Coverage |
|------|------|----------|
| Location capture | `LocationCaptureServiceTest.kt` | GPS acquisition |
| Navigation URI | `NavigationHelperTest.kt` | URI construction |
| Permission flow | Permission state tests | Grant/deny states |

### Web Tests

| Test | File | Coverage |
|------|------|----------|
| Map rendering | `MapPage.test.tsx` | Component render |
| API integration | `MapPage.test.tsx` | Data loading |

---

## 7. Regression Protection

### Existing Tests Must Pass

| Suite | Baseline |
|-------|----------|
| Backend unit | 240 passed |
| Backend integration | 135 passed |
| Frontend | 69 passed |
| Android | 49 passed |
| **Total** | **393 passed** |

---

## 8. Risk Assessment

| Risk | Mitigation |
|------|------------|
| Google Maps API key not configured | Graceful degradation, clear error messages |
| Location permission denied | Proper error states, manual fallback |
| GPS unavailable | Clear user messaging, retry option |
| PostGIS calculation performance | Proper indexing, query optimization |

---

## 9. Definition of Done

- [ ] Android Fused Location Provider captures real GPS
- [ ] Navigation intent opens Google Maps with fallback
- [ ] Location permissions handled at runtime
- [ ] Google Maps displays customer location
- [ ] Web map page shows customer/tenant data
- [ ] Distance traveled calculation works
- [ ] All existing tests still pass
- [ ] New tests added for new functionality
- [ ] No fake/hardcoded coordinates
- [ ] Visual identity unchanged
