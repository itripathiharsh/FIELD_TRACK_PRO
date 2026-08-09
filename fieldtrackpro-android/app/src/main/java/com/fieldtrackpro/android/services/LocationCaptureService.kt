package com.fieldtrackpro.android.services

import android.annotation.SuppressLint
import android.content.Context
import android.location.Location
import android.os.Looper
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
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
 * Service for capturing device location using Google's Fused Location Provider.
 *
 * Phase 4 Section 2: "Event-based location capture at check-in and check-out,
 * not a continuously updating live feed."
 *
 * Uses high accuracy GPS for check-in/out verification.
 */
class LocationCaptureService(private val context: Context) {

    private val fusedLocationClient: FusedLocationProviderClient =
        LocationServices.getFusedLocationProviderClient(context)

    /**
     * Capture the current device location.
     *
     * @return LocationResult with coordinates and metadata
     * @throws SecurityException if location permission not granted
     * @throws Exception if location unavailable
     */
    @SuppressLint("MissingPermission")
    suspend fun getCurrentLocation(): LocationResult = suspendCancellableCoroutine { cont ->
        val locationRequest = LocationRequest.Builder(
            Priority.PRIORITY_HIGH_ACCURACY,
            10000L
        ).apply {
            setWaitForAccurateLocation(true)
            setMinUpdateIntervalMillis(5000L)
        }.build()

        val callback = object : LocationCallback() {
            override fun onLocationResult(result: com.google.android.gms.location.LocationResult) {
                result.lastLocation?.let { location ->
                    if (cont.isActive) {
                        cont.resume(location.toLocationResult())
                        fusedLocationClient.removeLocationUpdates(this)
                    }
                } ?: run {
                    if (cont.isActive) {
                        cont.resumeWithException(Exception("Location unavailable"))
                        fusedLocationClient.removeLocationUpdates(this)
                    }
                }
            }
        }

        try {
            fusedLocationClient.requestLocationUpdates(
                locationRequest,
                callback,
                Looper.getMainLooper()
            )
        } catch (e: Exception) {
            if (cont.isActive) {
                cont.resumeWithException(e)
            }
        }

        cont.invokeOnCancellation {
            fusedLocationClient.removeLocationUpdates(callback)
        }
    }

    /**
     * Get the last known location (may be null).
     */
    @SuppressLint("MissingPermission")
    suspend fun getLastLocation(): LocationResult? = suspendCancellableCoroutine { cont ->
        fusedLocationClient.lastLocation
            .addOnSuccessListener { location ->
                if (cont.isActive) {
                    cont.resume(location?.toLocationResult())
                }
            }
            .addOnFailureListener { e ->
                if (cont.isActive) {
                    cont.resumeWithException(e)
                }
            }
    }

    private fun Location.toLocationResult(): LocationResult = LocationResult(
        latitude = latitude,
        longitude = longitude,
        accuracy = accuracy,
        isMockLocation = isFromMockProvider,
        timestamp = time
    )
}
