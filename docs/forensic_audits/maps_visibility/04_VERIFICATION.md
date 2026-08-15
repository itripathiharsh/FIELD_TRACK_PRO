# Maps Visibility Forensic Audit — Verification

**Date:** 2026-08-19

---

## 1. Web Verification

### Route Existence
```
File: src/App.tsx
Line 65: <Route path="/map" element={<AdminRoute><MapPage /></AdminRoute>} />
```
**Result:** Route exists and is registered.

### Sidebar Navigation
```
File: src/components/layout/sidebar.tsx
Lines 28-38: navItems = [
  { name: 'Dashboard', ... },
  { name: 'Employees', ... },
  { name: 'Territories', ... },
  { name: 'Customers', ... },
  { name: 'Visits', ... },
  { name: 'Geo Logs', ... },
  { name: 'Media Vault', ... },
  { name: 'Requirement Forms', ... },
  { name: 'Reports', ... },
]
```
**Result:** No Map entry. Map is unreachable from UI navigation.

### MapPage Component
```
File: src/pages/MapPage.tsx
- Uses FieldTrackMap component
- Fetches customers from API
- Filters valid coordinates
- Displays markers
```
**Result:** Component is functional and complete.

### FieldTrackMap Component
```
File: src/components/maps/FieldTrackMap.tsx
- Uses maplibre-gl
- Renders markers from props
- Has loading/error/empty states
```
**Result:** Component is functional and complete.

---

## 2. Android Verification

### MapScreen Component
```
File: ui/screens/maps/MapScreen.kt
- Uses MapLibre Android SDK
- Shows customer location marker
- Shows device location when available
- Handles permission states
```
**Result:** Component exists and is complete.

### Navigation Screen Sealed Class
```
File: ui/navigation/Screen.kt
sealed class Screen(val route: String) {
    object Splash : Screen("splash")
    object Login : Screen("login")
    object Dashboard : Screen("dashboard")
    object TodayVisits : Screen("today_visits")
    object VisitDetails : Screen("visit_details/{visitId}")
    object CheckIn : Screen("check_in/{visitId}/{customerId}")
    object CheckOut : Screen("check_out/{visitId}/{customerId}")
    object MediaUpload : Screen("media_upload/{visitId}")
    object ProfileSettings : Screen("profile_settings")
    object OfflineQueue : Screen("offline_queue")
}
```
**Result:** No Map screen defined. MapScreen is orphaned.

### NavGraph Routes
```
File: ui/navigation/NavGraph.kt
Lines 42-172: NavHost composables
```
**Result:** No MapScreen composable registered. MapScreen is unreachable.

### VisitDetailsScreen
```
File: ui/screens/visits/VisitDetailsScreen.kt
```
**Result:** No map preview embedded. Missing required feature per Screen List #6.

---

## 3. Backend Verification

### Customer Endpoint
```
GET /api/v1/customers
Response includes: location: { latitude, longitude }
```
**Result:** Backend correctly serves coordinates.

### PostGIS Storage
```
Table: customers
Column: location (geography(POINT, 4326))
```
**Result:** Spatial data correctly stored and queryable.

---

## 4. Summary

| Component | Exists | Wired | Visible |
|-----------|--------|-------|---------|
| Web MapPage | YES | Route only | **NO** (no Sidebar) |
| Web FieldTrackMap | YES | In MapPage | **NO** (no Sidebar) |
| Android MapScreen | YES | **NO** | **NO** |
| Android NavGraph | YES | No Map entry | **NO** |
| Backend APIs | YES | YES | YES |
