# Maps Visibility Repair — Plan

**Date:** 2026-08-19
**Based on:** docs/forensic_audits/maps_visibility/03_FINDINGS.md

---

## Defects to Repair

| ID | Severity | Description | Component |
|----|----------|-------------|-----------|
| D1 | HIGH | MapPage unreachable from Web UI (no Sidebar entry) | Web |
| D2 | HIGH | MapScreen not wired in Android navigation | Android |
| D3 | MEDIUM | VisitDetailsScreen missing map preview | Android |

---

## Repair Plan

### D1: Web — Add Map to Sidebar Navigation
- **File:** `src/components/layout/sidebar.tsx`
- **Change:** Add `{ name: 'Map', path: '/map', icon: MapPin, roles: ['ADMIN', 'MANAGER'] }` to navItems

### D2: Android — Wire MapScreen into Navigation
- **File:** `ui/navigation/Screen.kt` — Add `Screen.Map` sealed class entry
- **File:** `ui/navigation/NavGraph.kt` — Register MapScreen composable route
- **File:** `ui/screens/maps/MapScreen.kt` — Update to accept customerId and fetch data

### D3: Android — Add Map Preview to VisitDetailsScreen
- **File:** `ui/screens/visits/VisitDetailsScreen.kt` — Add map preview card with "View on Map" button
- **File:** `ui/navigation/NavGraph.kt` — Pass `onNavigateToMap` callback
