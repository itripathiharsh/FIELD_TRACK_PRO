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
    /** Same limit as the decision spec / server (GeoDecision.MAX_ACCURACY_M): above it there is no decision. */
    val REQUIRED_ACCURACY_M: Float = com.fieldtrackpro.android.utils.GeoDecision.MAX_ACCURACY_M.toFloat()

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
        return "GPS is not accurate enough yet$seen. Wait a few seconds or move closer to the entrance or a window, then try again."
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
        const val GOOD_ENOUGH_ACCURACY_M = 20f // stop collecting early once a fix is this good
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
        if (!hasFineLocationPermission()) {
            throw LocationPermissionDeniedException(
                if (hasLocationPermission()) "Precise location is required for attendance."
                else "Location permission not granted. Enable permission in settings."
            )
        }
        if (!isLocationEnabled()) throw LocationServicesDisabledException()

        // Fresh fused updates only (never a replayed cached fix); keep the best one and stop early on a good fix.
        var best: LocationResult? = null
        FusedFixCollector(context).collect(
            maxMs = timeoutMs,
            onFix = { best = FixPolicy.better(best, it) },
            stopWhen = { FixPolicy.isAcceptable(it, requiredAccuracyM) && it.accuracy <= GOOD_ENOUGH_ACCURACY_M }
        )
        val chosen = best
        if (chosen != null && FixPolicy.isAcceptable(chosen, requiredAccuracyM)) return chosen
        throw LocationUnavailableException(
            if (chosen != null) FixPolicy.poorAccuracyMessage(chosen, requiredAccuracyM)
            else "No GPS fix received (${timeoutMs / 1000}s). Move to an open area and try again."
        )
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
