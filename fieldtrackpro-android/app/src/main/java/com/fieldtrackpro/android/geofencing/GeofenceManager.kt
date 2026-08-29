package com.fieldtrackpro.android.geofencing

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.util.Log
import com.fieldtrackpro.android.utils.CoordinateValidator
import com.google.android.gms.location.Geofence
import com.google.android.gms.location.GeofencingClient
import com.google.android.gms.location.GeofencingRequest
import com.google.android.gms.location.LocationServices
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume

/**
 * Manages geofences for visit locations.
 *
 * Phase 4 Section 3: Geofencing Logic
 * APP-ATT-003: Asynchronous registration result verification before reporting monitoring state.
 */
class GeofenceManager(private val context: Context) {

    companion object {
        private const val TAG = "GeofenceManager"
        private const val GEOFENCE_EXPIRATION_NS = Geofence.NEVER_EXPIRE
        private const val GEOFENCE_LOITERING_DELAY_MS = 5000

        /**
         * The geofence id that must be removed before registering [newGeofenceId],
         * given whatever is currently monitored.
         */
        fun idToRemoveBeforeRegistering(currentGeofenceId: String?, newGeofenceId: String): String? {
            return currentGeofenceId?.takeIf { it != newGeofenceId }
        }
    }

    private val geofencingClient: GeofencingClient =
        LocationServices.getGeofencingClient(context)

    private val pendingIntent: PendingIntent by lazy {
        val intent = Intent(context, GeofenceBroadcastReceiver::class.java)
        PendingIntent.getBroadcast(
            context,
            0,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
    }

    /**
     * Register a geofence for a customer location and wait for async completion.
     *
     * @param geofenceId Unique ID for this geofence (e.g., visit ID)
     * @param latitude Customer latitude
     * @param longitude Customer longitude
     * @param radiusMeters Geofence radius in meters
     * @return true if registration succeeded on Play Services
     */
    suspend fun registerGeofence(
        geofenceId: String,
        latitude: Double,
        longitude: Double,
        radiusMeters: Float,
    ): Boolean = suspendCancellableCoroutine { cont ->
        if (!isValidCoordinate(latitude, longitude)) {
            Log.w(TAG, "Invalid coordinates for geofence: ($latitude, $longitude)")
            cont.resume(false)
            return@suspendCancellableCoroutine
        }

        val geofence = Geofence.Builder()
            .setRequestId(geofenceId)
            .setCircularRegion(latitude, longitude, radiusMeters)
            .setExpirationDuration(GEOFENCE_EXPIRATION_NS)
            .setTransitionTypes(
                Geofence.GEOFENCE_TRANSITION_ENTER or
                    Geofence.GEOFENCE_TRANSITION_EXIT or
                    Geofence.GEOFENCE_TRANSITION_DWELL
            )
            .setLoiteringDelay(GEOFENCE_LOITERING_DELAY_MS)
            .build()

        val request = GeofencingRequest.Builder()
            .setInitialTrigger(GeofencingRequest.INITIAL_TRIGGER_ENTER)
            .addGeofence(geofence)
            .build()

        try {
            geofencingClient.addGeofences(request, pendingIntent)
                .addOnSuccessListener {
                    Log.i(TAG, "Geofence registered: $geofenceId at ($latitude, $longitude) radius=${radiusMeters}m")
                    if (cont.isActive) cont.resume(true)
                }
                .addOnFailureListener { e ->
                    Log.e(TAG, "Failed to register geofence $geofenceId: ${e.message}")
                    if (cont.isActive) cont.resume(false)
                }
        } catch (e: SecurityException) {
            Log.e(TAG, "Missing location permission: ${e.message}")
            if (cont.isActive) cont.resume(false)
        } catch (e: Exception) {
            Log.e(TAG, "Error registering geofence: ${e.message}")
            if (cont.isActive) cont.resume(false)
        }
    }

    /**
     * Remove a specific geofence.
     */
    fun removeGeofence(geofenceId: String) {
        geofencingClient.removeGeofences(listOf(geofenceId))
            .addOnSuccessListener { Log.i(TAG, "Geofence removed: $geofenceId") }
            .addOnFailureListener { e -> Log.e(TAG, "Failed to remove geofence: ${e.message}") }
    }

    /**
     * Remove all registered geofences.
     */
    fun removeAllGeofences() {
        geofencingClient.removeGeofences(pendingIntent)
            .addOnSuccessListener { Log.i(TAG, "All geofences removed") }
            .addOnFailureListener { e -> Log.e(TAG, "Failed to remove geofences: ${e.message}") }
    }

    fun isValidCoordinate(lat: Double?, lng: Double?): Boolean {
        return CoordinateValidator.isValidCoordinate(lat, lng)
    }
}
