# Phase 6 — Maps, Geospatial Operations & Navigation
# MapLibre + OpenStreetMap Implementation

**Date:** 2026-08-09
**Decision:** MapLibre (Android + Web), OpenStreetMap tiles

---

## 1. Decision Summary

| Platform | Stack | Status |
|----------|-------|--------|
| Android | MapLibre SDK 11.8.0 | IMPLEMENTED |
| Web Admin | MapLibre GL JS | IMPLEMENTED |
| Tile Data | OpenStreetMap (configurable) | IMPLEMENTED |
| Geofencing Authority | PostgreSQL/PostGIS backend | PRESERVED |
| Distance Authority | PostgreSQL/PostGIS backend | PRESERVED |

---

## 2. What Was Implemented

### 2.1 Android MapLibre Integration

| File | Purpose |
|------|---------|
| `ui/screens/maps/MapScreen.kt` | Interactive map showing customer location |
| `services/LocationCaptureService.kt` | GPS capture via Android LocationManager (no Play Services) |
| `utils/NavigationHelper.kt` | Navigation deep-link with fallback |

**Features:**
- Customer location marker on interactive map
- Device location display when permission available
- Location permission denied state
- GPS disabled/unavailable state
- Loading, error, and empty states
- Invalid coordinate rejection (including Null Island)
- Navigation deep-link with fallback

### 2.2 Web MapLibre GL JS Integration

| File | Purpose |
|------|---------|
| `components/maps/FieldTrackMap.tsx` | Reusable MapLibre map component |
| `components/maps/tileConfig.ts` | Environment-driven tile provider config |
| `pages/MapPage.tsx` | Customer locations map page |

**Features:**
- Interactive map with customer markers
- Environment-configurable tile provider
- Loading/error/empty states
- No fake/demo geographic data
- Marker click for customer details

### 2.3 Tile Architecture

**Configuration:**
- Environment variable: `VITE_MAPLIBRE_TILE_URL` (web), `MAPLIBRE_TILE_URL` (Android)
- Default: MapLibre demo tiles (development only)
- Production: Configure commercial provider or self-hosted tiles

**Important:** Public/community tile services must not be abused for production traffic.
For production use, configure a commercial provider or self-hosted tile server.

### 2.4 Navigation (Preserved)

The existing navigation deep-link behavior is preserved:
- Primary: `google.navigation:q=lat,lng` (opens Google Maps app)
- Fallback: `geo:lat,lng?q=lat,lng(label)` (opens any maps app)
- Valid coordinates only (rejects Null Island)

---

## 3. What Was Already Correct (Untouched)

### Backend Geospatial

| Component | Status |
|-----------|--------|
| PostGIS ST_Distance on geography(POINT, 4326) | VERIFIED |
| Correct WKT ordering POINT(lng lat) | VERIFIED |
| Coordinate validation | VERIFIED |
| Mock location detection | VERIFIED |
| GPS accuracy threshold (100m) | VERIFIED |
| Audit logging | VERIFIED |
| No (0,0) fallback | VERIFIED |

---

## 4. Dependencies Added

### Android
```toml
maplibre-sdk = { group = "org.maplibre.gl", name = "android-sdk", version = "11.8.0" }
maplibre-annotations = { group = "org.maplibre.gl", name = "android-plugin-annotation-v9", version = "3.0.2" }
```

### Web
```json
"maplibre-gl": "^4.x"
```

### Removed
- Google Maps SDK for Android (play-services-maps, maps-compose)
- Google Play Services Location

---

## 5. Files Changed

### Android (4 files)
- `gradle/libs.versions.toml` - Replaced Google Maps with MapLibre
- `app/build.gradle.kts` - MapLibre dependencies, tile URL config
- `app/src/main/AndroidManifest.xml` - Removed Google Maps API key metadata
- `app/src/main/java/.../services/LocationCaptureService.kt` - Rewritten for LocationManager

### Web (4 files)
- `src/components/maps/FieldTrackMap.tsx` - New map component
- `src/components/maps/tileConfig.ts` - Tile provider configuration
- `src/pages/MapPage.tsx` - New map page
- `src/App.tsx` - Added map route

---

## 6. Test Results

| Suite | Count | Status |
|-------|-------|--------|
| Backend unit + integration | 240 | PASS |
| Frontend | 69 | PASS |
| Android | 49 | PASS |
| **Total** | **358** | **ALL PASS** |

---

## 7. Remaining Blockers

| Item | Reason |
|------|--------|
| Android MapLibre rendering | NOT_RUNTIME_VERIFIED - requires physical device |
| Web MapLibre rendering | NOT_RUNTIME_VERIFIED - requires browser |
| Google Maps navigation intent | NOT_RUNTIME_VERIFIED - requires physical device |
| Geofencing API | NOT_RUNTIME_VERIFIED - requires physical device |

These features are implemented at the code level but cannot be runtime-verified without a physical Android device or browser environment.

---

## 8. Environment Configuration

### Development
No configuration needed. Uses MapLibre demo tiles by default.

### Production
Set environment variables:
- Android: `MAPLIBRE_TILE_URL` in `local.properties`
- Web: `VITE_MAPLIBRE_TILE_URL` in `.env`

Example:
```
MAPLIBRE_TILE_URL=https://your-tile-server.com/style.json
```

---

## 9. Migration Notes

### From Google Maps
- Removed `play-services-maps`, `play-services-location`, `maps-compose`
- Removed `com.google.android.geo.API_KEY` metadata
- Location capture now uses Android's `LocationManager` (no Play Services dependency)
- Map rendering uses MapLibre SDK (open source, no API key required)

### Tile Provider
The tile provider is environment-configured and can be changed without
modifying map UI or business logic code.
