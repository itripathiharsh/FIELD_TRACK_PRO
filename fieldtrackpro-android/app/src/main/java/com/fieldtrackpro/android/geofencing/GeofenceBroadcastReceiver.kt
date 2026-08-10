package com.fieldtrackpro.android.geofencing

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import com.google.android.gms.location.Geofence
import com.google.android.gms.location.GeofenceStatusCodes
import com.google.android.gms.location.GeofencingEvent

/**
 * BroadcastReceiver for geofence transition events.
 *
 * Receives ENTER/DWELL/EXIT events from the Android Geofencing API
 * and updates the app state accordingly.
 */
class GeofenceBroadcastReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "GeofenceReceiver"
    }

    override fun onReceive(context: Context, intent: Intent) {
        val event = GeofencingEvent.fromIntent(intent)
        if (event == null) {
            Log.e(TAG, "GeofencingEvent is null")
            return
        }

        if (event.hasError()) {
            val errorMessage = GeofenceStatusCodes.getStatusCodeString(event.errorCode)
            Log.e(TAG, "Geofence error: $errorMessage")
            return
        }

        val transition = event.geofenceTransition
        val triggeringGeofences = event.triggeringGeofences ?: return

        for (geofence in triggeringGeofences) {
            when (transition) {
                Geofence.GEOFENCE_TRANSITION_ENTER -> {
                    Log.i(TAG, "ENTER geofence: ${geofence.requestId}")
                    GeofenceStateHolder.updateState(geofence.requestId, GeofenceState.INSIDE)
                }
                Geofence.GEOFENCE_TRANSITION_DWELL -> {
                    Log.i(TAG, "DWELL geofence: ${geofence.requestId}")
                    GeofenceStateHolder.updateState(geofence.requestId, GeofenceState.INSIDE)
                }
                Geofence.GEOFENCE_TRANSITION_EXIT -> {
                    Log.i(TAG, "EXIT geofence: ${geofence.requestId}")
                    GeofenceStateHolder.updateState(geofence.requestId, GeofenceState.OUTSIDE)
                }
                else -> {
                    Log.w(TAG, "Unknown geofence transition: $transition")
                }
            }
        }
    }
}

/**
 * Holds the current geofence state for all active geofences.
 * Used by the UI to display inside/outside status.
 */
enum class GeofenceState {
    UNKNOWN,
    INSIDE,
    OUTSIDE,
}

object GeofenceStateHolder {
    private val states = mutableMapOf<String, GeofenceState>()

    private val listeners = mutableListOf<(String, GeofenceState) -> Unit>()

    fun updateState(geofenceId: String, state: GeofenceState) {
        states[geofenceId] = state
        listeners.forEach { it(geofenceId, state) }
    }

    fun getState(geofenceId: String): GeofenceState {
        return states[geofenceId] ?: GeofenceState.UNKNOWN
    }

    fun addListener(listener: (String, GeofenceState) -> Unit) {
        listeners.add(listener)
    }

    fun removeListener(listener: (String, GeofenceState) -> Unit) {
        listeners.remove(listener)
    }

    fun clear() {
        states.clear()
    }
}
