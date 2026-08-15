# Maps Visibility Forensic Audit — Map Requirements

**Date:** 2026-08-19

---

## 1. Phase 6 Requirements (from planning documents)

### From `21_maps_location_services.md` (Phase 4)

**Web Maps:**
- "npm install @react-google-maps/api" → now MapLibre GL JS
- `<LoadScript googleMapsApiKey={...}>` → `<MapLibreMap>`
- "employeeMarkers.map(e => <MarkerF ...>)" → markers from real backend data
- **Admin "Live Map"** shows each employee's *last-known* location

**Android Maps:**
- Google Maps SDK integration → now MapLibre SDK
- Map preview on Visit Detail screen
- Navigate button (deep-link handoff to mapping app)

### From `11_android_screen_list.md` (Phase 2.5)

| # | Screen | Map Reference |
|---|--------|---------------|
| 6 | Visit Detail | "Customer info, **map preview**, Navigate + Start Visit buttons" |
| 7 | Navigation Handoff | "deep-links out to Google Maps app" |

---

## 2. Expected Map Locations

### Admin (Web): YES
- **Expected screen:** Customer Locations Map (overview of all customer locations)
- **Source:** Phase 4 "Web Setup" with employee/customer markers
- **Access:** Sidebar navigation or dedicated map page

### Sales/Employee (Android): YES
- **Expected screen:** Visit Detail (Screen #6)
- **Source:** Android Screen List — "map preview, Navigate + Start Visit buttons"
- **Access:** Visible on Visit Details screen

### Field Rep (Android): YES
- Same as Sales/Employee — Visit Detail screen should show map preview
