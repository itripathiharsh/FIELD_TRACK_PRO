# FieldTrack Pro — Maps & Location Services
### Phase 4 — Building the pieces Android needs before Android itself gets built
### Revision 2 — Section 5B's backend query rewritten for Python; everything else (Android, Maps SDK config, geofencing) is unchanged

This phase builds the location layer as reusable services/config — Android (Phase 6) and Web (Phase 7) both consume what's built here rather than each reinventing it.

---

## 1. Google Maps SDK Integration

*(Unchanged — Android and Web Maps setup has no dependency on backend language.)*

### Android Setup
```gradle
// app/build.gradle.kts
dependencies {
    implementation("com.google.android.gms:play-services-maps:19.0.0")
    implementation("com.google.android.gms:play-services-location:21.3.0")
    implementation("com.google.maps.android:maps-compose:6.2.1")
}
```

```xml
<!-- AndroidManifest.xml -->
<meta-data
    android:name="com.google.android.geo.API_KEY"
    android:value="${MAPS_API_KEY}" />
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
<uses-permission android:name="android.permission.ACCESS_BACKGROUND_LOCATION" />
```

### Web Setup
```bash
npm install @react-google-maps/api
```

```tsx
<LoadScript googleMapsApiKey={import.meta.env.VITE_MAPS_API_KEY}>
  <GoogleMap center={overviewCenter} zoom={11}>
    {employeeMarkers.map(e => <MarkerF key={e.id} position={e.lastKnownLocation} />)}
  </GoogleMap>
</LoadScript>
```

### API Key Restrictions (per Security Design Section 8 — restated here since this is where it actually gets configured)
- **Android key**: restricted by package name (`com.fieldtrackpro.android`) + SHA-1 signing fingerprint in Google Cloud Console.
- **Web key**: restricted by HTTP referrer (the dashboard's actual deployed domain).
- **Backend key** (used server-side for Geocoding/Distance APIs — separate from the two above): restricted by server IP, kept in the backend's `.env` file (loaded via `pydantic-settings`), never exposed to any client.
- Enable specifically: Maps SDK for Android, Maps JavaScript API, Geocoding API, Distance Matrix API (or Directions API if turn-by-turn ever moves in-app — currently it doesn't, see Section 4).

---

## 2. Live Location Tracking — Reconciling With the Locked Decision

*(Unchanged — this is a product/mobile decision, independent of backend language.)*

**Restating the Tech Stack/Requirements decision explicitly here**, since "Live Location tracking" is proposal language that could be misread as continuous GPS streaming: what's actually built is **event-based location capture at check-in and check-out**, not a continuously updating live feed. The admin's "Live Map" shows each employee's *last-known* location from their most recent check-in/check-out event.

### Android — Fused Location Provider (used only at the two capture moments)
```kotlin
class LocationCaptureService @Inject constructor(
    private val fusedLocationClient: FusedLocationProviderClient
) {
    suspend fun getCurrentLocation(): LocationResult {
        val location = fusedLocationClient.getCurrentLocation(
            Priority.PRIORITY_HIGH_ACCURACY,
            CancellationTokenSource().token
        ).await()

        return LocationResult(
            latitude = location.latitude,
            longitude = location.longitude,
            accuracy = location.accuracy,
            isMockLocation = location.isFromMockProvider   // per Security Design Section 7
        )
    }
}
```

**Why this matters to restate now**: it directly shapes battery usage (no background polling drain), data costs (no continuous upload stream), and the Android permission model (foreground location is sufficient for check-in/out; background location is only needed for the geofence-entry trigger in Section 3, which is a lighter-weight OS-level callback, not continuous app polling).

**If your actual field reality changes this** (e.g., managers want to see employees moving in real time, not just at two points), that's a real architecture change — background location service + periodic upload + battery/data cost increase — not a small tweak. Flagging clearly here since it's the single biggest scope lever in this whole phase, regardless of backend language.

---

## 3. Geofencing Logic

*(Android-side geofencing is unchanged. The backend note in this section is updated to reference the Python service.)*

### Backend — Already Built (Phase 3)
The actual verification (`ST_DWithin`) lives in `app/geo/verification.py` and `GeoVerificationService` (`app/services/geo_verification_service.py`) from the Database Implementation/Business Logic docs — Phase 4 doesn't duplicate this, it feeds it.

### Android — Geofencing API (Detects Arrival, Triggers the Check-in Prompt)
```kotlin
class GeofenceManager @Inject constructor(
    private val geofencingClient: GeofencingClient,
    private val context: Context
) {
    fun registerGeofence(visitId: String, lat: Double, lng: Double, radiusM: Float) {
        val geofence = Geofence.Builder()
            .setRequestId(visitId)
            .setCircularRegion(lat, lng, radiusM)
            .setExpirationDuration(Geofence.NEVER_EXPIRE)
            .setTransitionTypes(Geofence.GEOFENCE_TRANSITION_ENTER)
            .build()

        val request = GeofencingRequest.Builder()
            .setInitialTrigger(GeofencingRequest.INITIAL_TRIGGER_ENTER)
            .addGeofence(geofence)
            .build()

        geofencingClient.addGeofences(request, geofencePendingIntent)
    }
}
```

```kotlin
class GeofenceBroadcastReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val event = GeofencingEvent.fromIntent(intent) ?: return
        if (event.geofenceTransition == Geofence.GEOFENCE_TRANSITION_ENTER) {
            val visitId = event.triggeringGeofences?.firstOrNull()?.requestId ?: return
            // Show check-in confirmation prompt (Screen 9 from Android Screen List)
            NotificationHelper.showCheckInPrompt(context, visitId)
        }
    }
}
```

**Important distinction worth being explicit about**: Android's Geofencing API is a **convenience trigger** (tells the app "you've arrived, prompt the user") — it is NOT the security boundary. The actual verification happens server-side via `ST_DWithin` when the check-in request lands (Section 2's `GeoVerificationService`, now a FastAPI/GeoAlchemy2 implementation instead of Spring/Hibernate Spatial, with identical behavior). If the Android geofence fires falsely or is spoofed, the server-side check still catches it. This is the practical implementation of the E5 non-negotiable — restating it here because it's easy to conflate "client geofence" with "verification" and they are deliberately not the same thing, regardless of what backend language enforces it.

- **Geofence radius** comes from `customer.geofenceRadiusM` (fetched with the visit detail, default 75m per Database Design).
- Geofences are registered when the Visit Detail screen loads and removed when the visit completes or the employee navigates away — no need to hold more than the current day's geofences active at once (keeps Android's OS-level geofence limit, which is 100 per app, in no danger of being hit).

---

## 4. Route Navigation

*(Unchanged — Android-side deep-link handoff, no backend involvement at all.)*

**Decision, restating from User Flows**: navigation is a **deep-link handoff to the Google Maps app**, not in-app turn-by-turn. Building custom in-app navigation would mean licensing/implementing the Directions API's routing UI — real added cost and complexity for zero benefit over just handing off to an app every field employee already has and knows.

```kotlin
fun navigateToCustomer(context: Context, lat: Double, lng: Double, label: String) {
    val uri = Uri.parse("google.navigation:q=$lat,$lng")
    val intent = Intent(Intent.ACTION_VIEW, uri).apply {
        setPackage("com.google.android.apps.maps")
    }
    if (intent.resolveActivity(context.packageManager) != null) {
        context.startActivity(intent)
    } else {
        // Fallback: generic maps URI if Google Maps app isn't installed
        val fallbackUri = Uri.parse("geo:$lat,$lng?q=$lat,$lng($label)")
        context.startActivity(Intent(Intent.ACTION_VIEW, fallbackUri))
    }
}
```

The fallback matters — not every field device is guaranteed to have the Google Maps app installed (rare, but a cheap Android device might ship without it or have it disabled), so this degrades gracefully to whatever the OS's default maps handler is instead of crashing.

---

## 5. Distance Calculation

Two distinct distance calculations exist in this system, worth being precise about since they serve different purposes.

### A. Geofence Distance (Verification) — Already Built
`ST_Distance` inside `GeoVerificationService` (Phase 3, `app/geo/verification.py`) — this is the authoritative "how far is the employee from the customer right now" figure used for check-in validation and shown in the Flagged Visit Review screen.

### B. Total Distance Traveled (Productivity Report) — New in This Phase

**Rewritten for this revision** — this is the one genuine code change in this document. Cumulative distance across a day's visits, for the Productivity Dashboard (K3). Computed backend-side from the sequence of `check_in_location`/`check_out_location` points per employee per day, using a SQLAlchemy Core query with GeoAlchemy2's `ST_Distance`:

```python
# app/services/report_service.py
from sqlalchemy import select, func, text

async def calculate_daily_distance_traveled(db, employee_id, target_date) -> float | None:
    query = text("""
        SELECT SUM(
            ST_Distance(v1.check_out_location, v2.check_in_location)
        ) AS total_distance
        FROM visits v1
        JOIN visits v2 ON v2.employee_id = v1.employee_id
            AND v2.scheduled_at = (
                SELECT MIN(scheduled_at) FROM visits v3
                WHERE v3.employee_id = v1.employee_id
                AND v3.scheduled_at > v1.scheduled_at
                AND DATE(v3.scheduled_at) = DATE(v1.scheduled_at)
            )
        WHERE v1.employee_id = :employee_id AND DATE(v1.scheduled_at) = :target_date
    """)
    result = await db.execute(query, {"employee_id": str(employee_id), "target_date": target_date})
    return result.scalar()
```

This one query is written as raw parameterized SQL (via SQLAlchemy's `text()`, with bound parameters — no string concatenation, no injection risk) rather than GeoAlchemy2's expression API, since the correlated subquery (finding "the next visit that same day") is clearer as SQL than as chained ORM constructs. Same category of deliberate raw-SQL exception as the geo-fence check itself, for the same reason: it's parameterized and it's the product-critical calculation, not a shortcut.

**Honest limitation worth flagging, unchanged from the original**: since location is only captured at check-in/check-out (per the Section 2 decision), this distance figure is a **straight-line estimate between consecutive visit points**, not actual road-distance traveled. It's directionally useful for the Productivity Dashboard (busy day vs. light day) but shouldn't be presented as precise mileage — worth being clear about this in the UI copy itself ("approx. distance between visits") rather than implying GPS-tracked road mileage, so admins don't make decisions assuming false precision.

---

## Phase 4 — Complete

Google Maps SDK config, event-based location capture, geofence-trigger + server-verification split, navigation handoff, and both distance calculations are now built as reusable services — the Python backend query behaves identically to the original.

**Next up:** Phase 5 — File & Media Management (Image Upload, Document Upload, Digital Signatures, Storage Management) — the other service-layer piece Android needs before Phase 6 build starts.
