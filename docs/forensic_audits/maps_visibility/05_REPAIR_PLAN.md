# Maps Visibility Forensic Audit — Repair Plan

**Date:** 2026-08-19

---

## 1. Defects to Repair

| ID | Severity | Description | Component |
|----|----------|-------------|-----------|
| D1 | HIGH | Map unreachable from Web UI (no Sidebar) | Web |
| D2 | HIGH | MapScreen not wired in Android navigation | Android |
| D3 | MEDIUM | VisitDetailsScreen missing required map preview | Android |

---

## 2. Repair Plan

### 2.1 Web: Add Map to Sidebar Navigation

**File:** `src/components/layout/sidebar.tsx`

**Change:** Add Map entry to `navItems` array:
```tsx
{ name: 'Map', path: '/map', icon: Map, roles: ['ADMIN', 'MANAGER'] },
```

**Placement:** After 'Visits' entry (line 33), before 'Geo Logs'.

**Rationale:** Map is an admin/manager feature for viewing customer locations. The `Map` icon is already imported (line 6).

---

### 2.2 Android: Wire MapScreen into Navigation

#### 2.2.1 Add Map Screen to Screen Sealed Class

**File:** `ui/navigation/Screen.kt`

**Change:** Add Map entry:
```kotlin
object Map : Screen("map/{customerLat}/{customerLng}/{customerName}") {
    fun createRoute(customerLat: String, customerLng: String, customerName: String) =
        "map/$customerLat/$customerLng/$customerName"
}
```

#### 2.2.2 Register MapScreen in NavGraph

**File:** `ui/navigation/NavGraph.kt`

**Change:** Add composable route:
```kotlin
composable(
    route = Screen.Map.route,
    arguments = listOf(
        navArgument("customerLat") { type = NavType.StringType },
        navArgument("customerLng") { type = NavType.StringType },
        navArgument("customerName") { type = NavType.StringType }
    )
) { backStackEntry ->
    val lat = backStackEntry.arguments?.getString("customerLat")?.toDoubleOrNull()
    val lng = backStackEntry.arguments?.getString("customerLng")?.toDoubleOrNull()
    val name = backStackEntry.arguments?.getString("customerName") ?: ""
    MapScreen(
        customerLat = lat,
        customerLng = lng,
        customerName = name,
        onNavigateBack = { navController.popBackStack() },
        onNavigateToCustomer = { /* deep-link to maps app */ }
    )
}
```

---

### 2.3 Android: Add Map Preview to VisitDetailsScreen

**File:** `ui/screens/visits/VisitDetailsScreen.kt`

**Changes:**
1. Import MapScreen components
2. Add "View Map" button that navigates to MapScreen
3. OR embed a small map preview (preferred per Screen List #6)

**Preferred approach:** Embed a compact MapLibre view showing customer location, plus "Navigate" button for deep-link handoff.

---

## 3. Scope Exclusions

| Item | Reason |
|------|--------|
| MapLibre tile URL configuration | Out of scope — requires production infrastructure |
| Geofencing API implementation | Out of scope — requires physical device testing |
| Navigation deep-link testing | Out of scope — requires physical device |
| Web map styling/visual design | Out of scope — no design changes required |

---

## 4. Testing Plan

### Web Tests
- [ ] Verify Map appears in Sidebar for ADMIN role
- [ ] Verify Map appears in Sidebar for MANAGER role
- [ ] Verify Map does NOT appear for EMPLOYEE role
- [ ] Verify `/map` route loads MapPage
- [ ] Verify customer markers render from backend data

### Android Tests
- [ ] Verify Screen.Map route exists
- [ ] Verify MapScreen loads from navigation
- [ ] Verify VisitDetailsScreen has map preview or "View Map" button
- [ ] Verify navigation to MapScreen works

---

## 5. Risk Assessment

| Risk | Mitigation |
|------|------------|
| MapLibre tiles not loading | Document that production tile URL must be configured |
| Route parameter encoding | URL-encode customerName to handle special characters |
| Android navigation conflicts | Ensure unique route patterns |

---

## 6. Implementation Order

1. Web Sidebar fix (simplest, highest impact)
2. Android Screen + NavGraph wiring
3. Android VisitDetailsScreen map preview
4. Testing and verification
