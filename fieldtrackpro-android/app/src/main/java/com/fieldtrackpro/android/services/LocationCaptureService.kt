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
)

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
     * @throws SecurityException if location permission not granted
     * @throws Exception if location unavailable
     */
    suspend fun getCurrentLocation(): LocationResult = suspendCancellableCoroutine { cont ->
        if (!hasLocationPermission()) {
            cont.resumeWithException(SecurityException("Location permission not granted"))
            return@suspendCancellableCoroutine
        }

        if (!isLocationEnabled()) {
            cont.resumeWithException(Exception("Location services are disabled"))
            return@suspendCancellableCoroutine
        }

        val providers = listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)
        var locationReceived = false

        for (provider in providers) {
            if (!locationManager.isProviderEnabled(provider)) continue

            // Try getting last known location first
            try {
                val lastLocation = locationManager.getLastKnownLocation(provider)
                if (lastLocation != null && !locationReceived) {
                    locationReceived = true
                    cont.resume(lastLocation.toLocationResult())
                    return@suspendCancellableCoroutine
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
                    5000L, // min time between updates (ms)
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
                cont.resumeWithException(Exception("Unable to determine location. Please ensure GPS is enabled."))
            }
        }
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
