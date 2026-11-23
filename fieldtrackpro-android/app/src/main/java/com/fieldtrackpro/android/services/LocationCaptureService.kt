package com.fieldtrackpro.android.services

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Bundle
import android.os.Looper
import androidx.core.content.ContextCompat
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeout
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/**
 * Result of a location capture attempt.
 */
data class LocationResult(
    val latitude: Double,
    val longitude: Double,
    val accuracy: Float,
    val isMockLocation: Boolean,
    val timestamp: Long
) {
    /**
     * Age of this fix in milliseconds.
     */
    fun ageMillis(nowMillis: Long = System.currentTimeMillis()): Long = nowMillis - timestamp

    /** True when [accuracy] is within acceptable threshold. */
    val isAccuracyAcceptable: Boolean
        get() = accuracy <= LocationCaptureService.MAX_ACCURACY_THRESHOLD_M
}

class LocationPermissionDeniedException(message: String = "Location permission not granted. Enable permission in settings.") : SecurityException(message)
class LocationServicesDisabledException(message: String = "Location services are disabled. Please turn on GPS.") : Exception(message)
/**
 * Pure rules for choosing a GPS fix (no Android types, unit-tested on the JVM).
 *
 * ROOT CAUSE of "449 m away after moving two steps": getCurrentLocation() used to return the FIRST fix delivered by
 * either provider, whatever its accuracy. Right after the camera closes the first delivery is usually a coarse NETWORK
 * fix (+-400 m or more), so the distance card measured from a point hundreds of metres off the real position.
 */
object FixPolicy {
    /** A fix must be at least this accurate to be used for distance / check-in. */
    const val REQUIRED_ACCURACY_M = 50f

    /** Android reports 0 when a location has no accuracy at all; treat that (and NaN) as unknown, i.e. unusable. */
    fun accuracyKnown(accuracyM: Float): Boolean = !accuracyM.isNaN() && accuracyM > 0f && accuracyM != Float.MAX_VALUE

    fun isAcceptable(fix: LocationResult, requiredAccuracyM: Float = REQUIRED_ACCURACY_M, nowMillis: Long = System.currentTimeMillis()): Boolean =
        accuracyKnown(fix.accuracy) && fix.accuracy <= requiredAccuracyM &&
            fix.ageMillis(nowMillis) in -1_000L..LocationCaptureService.MAX_FRESHNESS_MS

    /** Keeps the more accurate of two fixes. */
    fun better(current: LocationResult?, candidate: LocationResult): LocationResult =
        if (current == null || !accuracyKnown(current.accuracy) || (accuracyKnown(candidate.accuracy) && candidate.accuracy < current.accuracy)) candidate else current

    fun poorAccuracyMessage(best: LocationResult?, requiredAccuracyM: Float = REQUIRED_ACCURACY_M): String {
        val seen = best?.takeIf { accuracyKnown(it.accuracy) }?.let { " (best fix was +-${it.accuracy.toInt()} m)" } ?: ""
        return "GPS is not accurate enough yet$seen. Move to an open area and wait until accuracy is within " +
            "${requiredAccuracyM.toInt()} m, then try again."
    }
}

class LocationUnavailableException(message: String = "Unable to determine location within timeout. Move to open sky and try again.") : Exception(message)

/**
 * Service for capturing device location using Android's standard LocationManager.
 *
 * APP-ATT-001: Strict GPS freshness enforcement (<= 30s) for attendance capture.
 * APP-ATT-002: Guaranteed listener unregistration across success, timeout, and cancellation.
 * APP-ATT-004: Explicit handling of fine vs coarse permissions.
 */
class LocationCaptureService(private val context: Context) {

    companion object {
        const val MAX_ACCURACY_THRESHOLD_M = 100.0f
        const val LOCATION_TIMEOUT_MS = 30_000L
        const val MAX_FRESHNESS_MS = 30_000L // 30 seconds maximum age for attendance fixes

        /**
         * Calculates geodesic distance between two points in meters using Haversine formula.
         */
        fun calculateDistanceM(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Double {
            val r = 6371000.0 // Earth radius in meters
            val phi1 = Math.toRadians(lat1)
            val phi2 = Math.toRadians(lat2)
            val dPhi = Math.toRadians(lat2 - lat1)
            val dLambda = Math.toRadians(lon2 - lon1)

            val a = Math.sin(dPhi / 2.0) * Math.sin(dPhi / 2.0) +
                Math.cos(phi1) * Math.cos(phi2) *
                Math.sin(dLambda / 2.0) * Math.sin(dLambda / 2.0)
            val c = 2.0 * Math.atan2(Math.sqrt(a), Math.sqrt(1.0 - a))
            return r * c
        }
    }

    private val locationManager: LocationManager =
        context.getSystemService(Context.LOCATION_SERVICE) as LocationManager

    /**
     * Check if precise (fine) location permission is granted.
     */
    fun hasFineLocationPermission(): Boolean {
        return ContextCompat.checkSelfPermission(
            context, Manifest.permission.ACCESS_FINE_LOCATION
        ) == PackageManager.PERMISSION_GRANTED
    }

    /**
     * Check if any location permission (fine or coarse) is granted.
     */
    fun hasLocationPermission(): Boolean {
        return hasFineLocationPermission() ||
            ContextCompat.checkSelfPermission(
                context, Manifest.permission.ACCESS_COARSE_LOCATION
            ) == PackageManager.PERMISSION_GRANTED
    }

    /**
     * Check if GPS/location services are enabled.
     */
    fun isLocationEnabled(): Boolean {
        return locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER) ||
            locationManager.isProviderEnabled(LocationManager.NETWORK_PROVIDER)
    }

    /**
     * Capture the current device location with a timeout.
     *
     * APP-ATT-001: Rejects any location older than 30 seconds.
     * APP-ATT-002: Guaranteed listener unregistration.
     *
     * @return LocationResult with coordinates and metadata
     * @throws LocationPermissionDeniedException if location permission not granted
     * @throws LocationServicesDisabledException if location services are disabled
     * @throws LocationUnavailableException if location unavailable or timed out
     */
    suspend fun getCurrentLocation(
        timeoutMs: Long = LOCATION_TIMEOUT_MS,
        requiredAccuracyM: Float = FixPolicy.REQUIRED_ACCURACY_M
    ): LocationResult {
        // Best fix seen so far, kept only to tell the employee how close we got.
        val best = java.util.concurrent.atomic.AtomicReference<LocationResult?>(null)
        return try {
            withTimeout(timeoutMs) {
                getCurrentLocationInternal(requiredAccuracyM, best)
            }
        } catch (e: kotlinx.coroutines.TimeoutCancellationException) {
            // Last-known is only a fallback when it is BOTH fresh (<= 30 s) and accurate enough.
            val fallback = getLastLocationInternal()
            if (fallback != null && FixPolicy.isAcceptable(fallback, requiredAccuracyM)) {
                fallback
            } else {
                val seen = best.get()?.let { FixPolicy.better(it, fallback ?: it) } ?: fallback
                throw LocationUnavailableException(
                    if (seen != null) FixPolicy.poorAccuracyMessage(seen, requiredAccuracyM)
                    else "No GPS fix received (${timeoutMs / 1000}s). Move to an open area and try again."
                )
            }
        }
    }

    private suspend fun getCurrentLocationInternal(
        requiredAccuracyM: Float,
        best: java.util.concurrent.atomic.AtomicReference<LocationResult?>
    ): LocationResult = suspendCancellableCoroutine { cont ->
        if (!hasFineLocationPermission()) {
            if (hasLocationPermission()) {
                cont.resumeWithException(LocationPermissionDeniedException("Precise location is required for attendance."))
            } else {
                cont.resumeWithException(LocationPermissionDeniedException("Location permission not granted. Enable permission in settings."))
            }
            return@suspendCancellableCoroutine
        }

        if (!isLocationEnabled()) {
            cont.resumeWithException(LocationServicesDisabledException())
            return@suspendCancellableCoroutine
        }

        val providers = listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)
        var locationReceived = false
        val registeredListeners = mutableListOf<LocationListener>()

        for (provider in providers) {
            if (!locationManager.isProviderEnabled(provider)) continue

            // Try getting last known location first only if it's strictly fresh (<= 30 seconds)
            try {
                val lastLocation = locationManager.getLastKnownLocation(provider)
                if (lastLocation != null && !locationReceived) {
                    val candidate = lastLocation.toLocationResult()
                    best.set(FixPolicy.better(best.get(), candidate))
                    // Fresh AND accurate enough; a coarse cached network fix is not good enough to measure distance.
                    if (FixPolicy.isAcceptable(candidate, requiredAccuracyM)) {
                        locationReceived = true
                        cleanupListeners(registeredListeners)
                        cont.resume(candidate)
                        return@suspendCancellableCoroutine
                    }
                }
            } catch (e: SecurityException) {
                // Permission issue, continue
            }

            // Request fresh asynchronous location
            val listener = object : LocationListener {
                override fun onLocationChanged(location: Location) {
                    if (locationReceived) return
                    val candidate = location.toLocationResult()
                    best.set(FixPolicy.better(best.get(), candidate))
                    // Keep listening until a fix is accurate enough: the first delivery is often a coarse network fix.
                    if (!FixPolicy.isAcceptable(candidate, requiredAccuracyM)) return
                    locationReceived = true
                    cleanupListeners(registeredListeners)
                    if (cont.isActive) cont.resume(candidate)
                }

                @Deprecated("Deprecated in API 29")
                override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) {}
                override fun onProviderEnabled(provider: String) {}
                override fun onProviderDisabled(provider: String) {}
            }

            registeredListeners.add(listener)

            try {
                locationManager.requestLocationUpdates(
                    provider,
                    1000L, // min time between updates (ms)
                    0f,    // min distance between updates (m)
                    listener,
                    Looper.getMainLooper()
                )
            } catch (e: SecurityException) {
                // Permission issue, continue to next provider
            }
        }

        cont.invokeOnCancellation {
            cleanupListeners(registeredListeners)
        }
    }

    fun cleanupListeners(listeners: List<LocationListener>) {
        for (l in listeners) {
            try {
                locationManager.removeUpdates(l)
            } catch (e: Exception) {
                // Ignore removal failure
            }
        }
    }

    private fun getLastLocationInternal(): LocationResult? {
        if (!hasLocationPermission()) return null
        val providers = listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)
        for (provider in providers) {
            try {
                if (locationManager.isProviderEnabled(provider)) {
                    val loc = locationManager.getLastKnownLocation(provider)
                    if (loc != null) return loc.toLocationResult()
                }
            } catch (e: SecurityException) {
                // ignore
            }
        }
        return null
    }

    /**
     * Get the last known location only if fresh.
     */
    suspend fun getLastLocation(): LocationResult? {
        return getLastLocationInternal()
    }

    private fun Location.toLocationResult(): LocationResult = LocationResult(
        latitude = latitude,
        longitude = longitude,
        // hasAccuracy() == false means "unknown", which must never look like a perfect 0 m fix.
        accuracy = if (hasAccuracy()) accuracy else Float.MAX_VALUE,
        isMockLocation = if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
            isMock
        } else {
            @Suppress("DEPRECATION")
            isFromMockProvider
        },
        timestamp = time
    )
}
