package com.fieldtrackpro.android.services

import android.content.Context
import android.location.Location
import android.os.Looper
import android.os.SystemClock
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/**
 * Collects FRESH fused location updates for up to [maxMs]. Nothing cached is replayed: the request asks for high
 * accuracy at 1 s intervals, and each fix carries the wall-clock time it was actually taken (derived from the monotonic
 * clock, not from Location.time, which some devices report wrongly).
 *
 * The caller decides when to stop ([stopWhen]) and what to keep (see [FixSelector]).
 */
class FusedFixCollector(private val context: Context) {

    suspend fun collect(
        maxMs: Long = MAX_WINDOW_MS,
        onFix: (LocationResult) -> Unit,
        stopWhen: (LocationResult) -> Boolean = { false }
    ) {
        val client = LocationServices.getFusedLocationProviderClient(context)
        val request = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 1000L)
            .setMinUpdateIntervalMillis(500L)
            .setWaitForAccurateLocation(false)
            .setMaxUpdateAgeMillis(5_000L)
            .build()
        var callback: LocationCallback? = null
        try {
            withTimeoutOrNull(maxMs) {
                suspendCancellableCoroutine<Unit> { cont ->
                    val cb = object : LocationCallback() {
                        override fun onLocationResult(result: com.google.android.gms.location.LocationResult) {
                            for (loc in result.locations) {
                                val fix = loc.toFix()
                                onFix(fix)
                                if (stopWhen(fix)) {
                                    if (cont.isActive) cont.resume(Unit)
                                    return
                                }
                            }
                        }
                    }
                    callback = cb
                    try {
                        client.requestLocationUpdates(request, cb, Looper.getMainLooper())
                    } catch (e: SecurityException) {
                        cont.resumeWithException(LocationPermissionDeniedException())
                    }
                }
            }
        } finally {
            callback?.let { client.removeLocationUpdates(it) }
        }
    }

    companion object {
        /** Upper bound of one collection window (spec: up to 45 s). */
        const val MAX_WINDOW_MS = 45_000L

        internal fun Location.toFix(): LocationResult {
            val ageMs = ((SystemClock.elapsedRealtimeNanos() - elapsedRealtimeNanos) / 1_000_000L).coerceAtLeast(0L)
            return LocationResult(
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
                timestamp = System.currentTimeMillis() - ageMs
            )
        }
    }
}
