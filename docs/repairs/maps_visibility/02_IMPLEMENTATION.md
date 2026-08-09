# Maps Visibility Repair — Implementation

**Date:** 2026-08-19

---

## Changes Made

### 1. Web — Sidebar Navigation (D1)

**File:** `src/components/layout/sidebar.tsx`

```tsx
const navItems = [
    { name: 'Dashboard', path: '/', icon: LayoutDashboard, roles: ['ADMIN', 'MANAGER', 'EMPLOYEE'] },
    { name: 'Employees', path: '/employees', icon: Users, roles: ['ADMIN', 'MANAGER'] },
    { name: 'Territories', path: '/territories', icon: Map, roles: ['ADMIN', 'MANAGER'] },
    { name: 'Customers', path: '/customers', icon: Building2, roles: ['ADMIN', 'MANAGER'] },
    { name: 'Visits', path: '/visits', icon: CalendarCheck, roles: ['ADMIN', 'MANAGER', 'EMPLOYEE'] },
    { name: 'Map', path: '/map', icon: MapPin, roles: ['ADMIN', 'MANAGER'] },  // <-- ADDED
    { name: 'Geo Logs', path: '/geo-logs', icon: MapPin, roles: ['ADMIN', 'MANAGER'] },
    ...
];
```

**Result:** Map page now accessible from Sidebar for ADMIN and MANAGER roles.

---

### 2. Android — MapScreen Navigation (D2)

**File:** `ui/navigation/Screen.kt`

```kotlin
sealed class Screen(val route: String) {
    // ... existing entries ...
    object Map : Screen("map/{customerId}") {
        fun createRoute(customerId: String) = "map/$customerId"
    }
}
```

**File:** `ui/navigation/NavGraph.kt`

```kotlin
composable(
    route = Screen.Map.route,
    arguments = listOf(navArgument("customerId") { type = NavType.StringType })
) { backStackEntry ->
    val customerId = backStackEntry.arguments?.getString("customerId") ?: ""
    MapScreen(
        customerId = customerId,
        onNavigateBack = { navController.popBackStack() }
    )
}
```

**File:** `ui/screens/maps/MapScreen.kt`
- Changed signature from `(customerLat, customerLng, customerName, ...)` to `(customerId, onNavigateBack)`
- Fetches customer data from API using CustomerRepository
- Displays map with customer marker

**Result:** MapScreen is now reachable via navigation.

---

### 3. Android — VisitDetailsScreen Map Preview (D3)

**File:** `ui/screens/visits/VisitDetailsScreen.kt`

```kotlin
@Composable
fun VisitDetailsScreen(
    visitId: String,
    viewModel: VisitDetailsViewModel,
    onNavigateBack: () -> Unit,
    onNavigateToCheckIn: (String, String) -> Unit,
    onNavigateToCheckOut: (String, String) -> Unit,
    onNavigateToMedia: (String) -> Unit,
    onNavigateToMap: (String) -> Unit = {}  // <-- ADDED
) {
    // ... existing code ...

    // Map Preview Section (Android Screen List #6)
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(text = "Customer Location", ...)
            Text(text = "View customer location on map and get directions.", ...)
            OutlinedButton(
                onClick = { onNavigateToMap(visit.customerId) },
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("VIEW ON MAP")
            }
        }
    }
}
```

**File:** `ui/navigation/NavGraph.kt`

```kotlin
VisitDetailsScreen(
    visitId = visitId,
    viewModel = visitDetailsViewModel,
    onNavigateBack = { navController.popBackStack() },
    onNavigateToCheckIn = { vId, cId -> navController.navigate(Screen.CheckIn.createRoute(vId, cId)) },
    onNavigateToCheckOut = { vId, cId -> navController.navigate(Screen.CheckOut.createRoute(vId, cId)) },
    onNavigateToMedia = { vId -> navController.navigate(Screen.MediaUpload.createRoute(vId)) },
    onNavigateToMap = { cId -> navController.navigate(Screen.Map.createRoute(cId)) }  // <-- ADDED
)
```

**Result:** VisitDetailsScreen now shows map preview with "View on Map" button.

---

## Files Changed

| File | Change |
|------|--------|
| `fieldtrackpro-web/src/components/layout/sidebar.tsx` | Added Map entry to navItems |
| `fieldtrackpro-android/.../ui/navigation/Screen.kt` | Added Screen.Map sealed class entry |
| `fieldtrackpro-android/.../ui/navigation/NavGraph.kt` | Registered MapScreen route + onNavigateToMap callback |
| `fieldtrackpro-android/.../ui/screens/maps/MapScreen.kt` | Updated to accept customerId, fetch from API |
| `fieldtrackpro-android/.../ui/screens/visits/VisitDetailsScreen.kt` | Added map preview card + onNavigateToMap param |
