# Maps Visibility Forensic Audit — Findings

**Date:** 2026-08-19

---

## 1. Expected vs Actual Map Locations

### Admin (Web)

| Aspect | Expected | Actual |
|--------|----------|--------|
| Map visible | YES | **NO** |
| Screen | Customer Locations Map | MapPage exists but **not in Sidebar** |
| Route | `/map` | `/map` exists, registered in App.tsx |
| Access | Sidebar navigation | **No Sidebar entry** — unreachable from UI |

### Sales/Employee (Android)

| Aspect | Expected | Actual |
|--------|----------|--------|
| Map visible | YES | **NO** |
| Screen | Visit Detail (Screen #6) | VisitDetailsScreen has **no map** |
| Route | `visit_details/{visitId}` | Route exists but no map component |
| Access | Visit Detail screen | **Map not wired** — unreachable |

---

## 2. Actual Current State

### What EXISTS

**Web:**
- `src/pages/MapPage.tsx` — Full page with FieldTrackMap component
- `src/components/maps/FieldTrackMap.tsx` — Reusable MapLibre map component
- `src/components/maps/tileConfig.ts` — Environment-configurable tile provider
- Route registered: `<Route path="/map" element={<AdminRoute><MapPage /></AdminRoute>} />`

**Android:**
- `ui/screens/maps/MapScreen.kt` — MapLibre map screen with customer marker
- `services/LocationCaptureService.kt` — GPS capture via LocationManager
- `utils/NavigationHelper.kt` — Navigation deep-link with fallback

**Backend:**
- Customer locations served via GET /api/v1/customers (includes `location: {latitude, longitude}`)
- All coordinates stored in PostGIS geography(POINT, 4326)

### What is WIRED

**Web:**
- ✅ MapPage route registered in App.tsx
- ❌ MapPage NOT in Sidebar navigation items
- ❌ MapPage NOT linked from any existing page

**Android:**
- ❌ MapScreen NOT in Screen sealed class
- ❌ MapScreen NOT registered in NavGraph
- ❌ VisitDetailsScreen does NOT embed MapScreen
- ❌ No navigation path leads to MapScreen

### What is VISIBLE

**Web:**
- ❌ Map cannot be accessed from UI (no Sidebar link)
- ❌ Map is accessible only by typing `/map` URL directly
- ❌ Even then, MapLibre tiles may not render without proper tile URL configuration

**Android:**
- ❌ Map is completely invisible — no navigation path exists

---

## 3. Root Cause

### Web Root Cause
The MapPage component and route exist but are **not exposed in the Sidebar navigation**. The Sidebar (`Sidebar.tsx`) has no entry for the `/map` route, making the map unreachable from the UI.

### Android Root Cause
The MapScreen component exists but is **not wired into the navigation system**:
1. No `Screen.Map` entry in the `Screen` sealed class
2. No `composable(Screen.Map.route)` in `NavGraph`
3. `VisitDetailsScreen` does not embed or link to MapScreen
4. The Android Screen List requires a "map preview" on Visit Detail, but this was not implemented

---

## 4. Defects Found

| ID | Severity | Area | Description |
|----|----------|------|-------------|
| D1 | **HIGH** | Web | MapPage not in Sidebar — unreachable from UI |
| D2 | **HIGH** | Android | MapScreen not in NavGraph — completely invisible |
| D3 | **MEDIUM** | Android | VisitDetailsScreen missing required map preview (per Screen List #6) |
| D4 | **LOW** | Web | MapLibre tiles may not render without production tile URL (development-only default) |

---

## 5. What Needs to Be Fixed

### Web Fixes
1. **Add MapPage to Sidebar navigation** in `Sidebar.tsx`
   - Add entry: `{ name: 'Map', path: '/map', icon: Map, roles: ['ADMIN', 'MANAGER'] }`

### Android Fixes
1. **Add MapScreen to Screen sealed class** in `Screen.kt`
   - Add: `object Map : Screen("map/{customerLat}/{customerLng}/{customerName}")`
2. **Register MapScreen in NavGraph** in `NavGraph.kt`
   - Add composable route for MapScreen
3. **Embed map preview in VisitDetailsScreen** OR add "View Map" button
   - Per Screen List #6: "Customer info, map preview, Navigate + Start Visit buttons"

---

## 6. Verification Performed

| Check | Result |
|-------|--------|
| MapPage exists | YES (`src/pages/MapPage.tsx`) |
| MapPage route registered | YES (`App.tsx:65`) |
| MapPage in Sidebar | **NO** — missing from `Sidebar.tsx` |
| FieldTrackMap component exists | YES |
| tileConfig exists | YES |
| MapScreen exists (Android) | YES (`ui/screens/maps/MapScreen.kt`) |
| MapScreen in Screen sealed class | **NO** |
| MapScreen in NavGraph | **NO** |
| VisitDetailsScreen has map | **NO** |
| Backend serves coordinates | YES (`GET /api/v1/customers`) |
