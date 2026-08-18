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
     * P1-9: age of this fix, so a caller can judge freshness. No hard
     * staleness cutoff is enforced anywhere in this codebase yet - see
     * LocationCaptureService.MAX_ACCURACY_THRESHOLD_M's doc comment for why
     * a freshness threshold specifically was deliberately NOT invented here.
     */
    fun ageMillis(nowMillis: Long = System.currentTimeMillis()): Long = nowMillis - timestamp

    /** True when [accuracy] exceeds LocationCaptureService.MAX_ACCURACY_THRESHOLD_M. */
    val isAccuracyAcceptable: Boolean
        get() = accuracy <= LocationCaptureService.MAX_ACCURACY_THRESHOLD_M
}

class LocationPermissionDeniedException(message: String = "Location permission not granted. Enable permission in settings.") : SecurityException(message)
class LocationServicesDisabledException(message: String = "Location services are disabled. Please turn on GPS.") : Exception(message)
class LocationUnavailableException(message: String = "Unable to determine location. Move to open sky and try again.") : Exception(message)

/**
 * Service for capturing device location using Android's standard LocationManager.
 *
 * Phase 4 Section 2: "Event-based location capture at check-in and check-out,
 * not a continuously updating live feed."
 *
 * Uses Android's built-in LocationManager (no Google Play Services required),
 * making it compatible with MapLibre and devices without Google Play.
 */
class LocationCaptureService(private val context: Context) {

    companion object {
        /**
         * P1-9: mirrors GeoVerificationService.MAX_ACCURACY_THRESHOLD_M on
         * the backend exactly (app/services/geo_verification_service.py),
         * so the client warns about a fix the server will reject anyway,
         * instead of only finding out after a round trip. Reused, not
         * invented - the server remains authoritative regardless.
         */
        const val MAX_ACCURACY_THRESHOLD_M = 100.0f

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
     * Check if location permissions are granted.
     */
    fun hasLocationPermission(): Boolean {
        return ContextCompat.checkSelfPermission(
            context, Manifest.permission.ACCESS_FINE_LOCATION
        ) == PackageManager.PERMISSION_GRANTED ||
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
     * Capture the current device location.
     *
     * @return LocationResult with coordinates and metadata
     * @throws LocationPermissionDeniedException if location permission not granted
     * @throws LocationServicesDisabledException if location services are disabled
     * @throws LocationUnavailableException if location unavailable
     */
    suspend fun getCurrentLocation(): LocationResult = suspendCancellableCoroutine { cont ->
        if (!hasLocationPermission()) {
            cont.resumeWithException(LocationPermissionDeniedException())
            return@suspendCancellableCoroutine
        }

        if (!isLocationEnabled()) {
            cont.resumeWithException(LocationServicesDisabledException())
            return@suspendCancellableCoroutine
        }

        val providers = listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)
        var locationReceived = false

        for (provider in providers) {
            if (!locationManager.isProviderEnabled(provider)) continue

            // Try getting last known location first if it's fresh (< 60 seconds)
            try {
                val lastLocation = locationManager.getLastKnownLocation(provider)
                if (lastLocation != null && !locationReceived) {
                    val ageMs = System.currentTimeMillis() - lastLocation.time
                    if (ageMs < 60000L) {
                        locationReceived = true
                        cont.resume(lastLocation.toLocationResult())
                        return@suspendCancellableCoroutine
                    }
                }
            } catch (e: SecurityException) {
                // Permission issue, continue
            }

            // Request fresh location
            val listener = object : LocationListener {
                override fun onLocationChanged(location: Location) {
                    if (!locationReceived) {
                        locationReceived = true
                        locationManager.removeUpdates(this)
                        if (cont.isActive) {
                            cont.resume(location.toLocationResult())
                        }
                    }
                }

                @Deprecated("Deprecated in API 29")
                override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) {}

                override fun onProviderEnabled(provider: String) {}

                override fun onProviderDisabled(provider: String) {
                    if (!locationReceived) {
                        locationManager.removeUpdates(this)
                    }
                }
            }

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
            // Clean up listeners on cancellation
        }

        if (!locationReceived) {
            if (cont.isActive) {
                // Fallback to last known location if available before throwing
                val fallback = getLastLocationInternal()
                if (fallback != null) {
                    cont.resume(fallback)
                } else {
                    cont.resumeWithException(LocationUnavailableException())
                }
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
     * Get the last known location (may be null).
     */
    suspend fun getLastLocation(): LocationResult? {
        if (!hasLocationPermission()) return null

        val providers = listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)

        for (provider in providers) {
            try {
                if (locationManager.isProviderEnabled(provider)) {
                    val location = locationManager.getLastKnownLocation(provider)
                    if (location != null) return location.toLocationResult()
                }
            } catch (e: SecurityException) {
                // Permission issue, continue
            }
        }
        return null
    }

    private fun Location.toLocationResult(): LocationResult = LocationResult(
        latitude = latitude,
        longitude = longitude,
        accuracy = accuracy,
        isMockLocation = if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
            isMock
        } else {
            @Suppress("DEPRECATION")
            isFromMockProvider
        },
        timestamp = time
    )
}
