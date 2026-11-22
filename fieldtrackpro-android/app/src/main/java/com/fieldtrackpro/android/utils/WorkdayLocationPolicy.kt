package com.fieldtrackpro.android.utils

/**
 * Decides whether a GPS fix may be used to start or end a workday.
 *
 * The dashboard used to fall back to (0.0, 0.0) when GPS failed and submit End Day anyway, writing a point in the
 * Gulf of Guinea into the attendance record. A workday action is now only submitted with a fix that:
 *  - exists and has valid, non-(0,0) coordinates ([CoordinateValidator]),
 *  - is not from a mock-location provider,
 *  - has a usable accuracy no worse than [MAX_ACCURACY_M].
 *
 * [MAX_ACCURACY_M] is looser than the 100 m check-in threshold on purpose: Start/End Day often happens indoors at the
 * depot, and the backend does not geofence workday events. It still rejects fixes too vague to mean anything.
 */
object WorkdayLocationPolicy {

    const val MAX_ACCURACY_M = 250.0

    sealed class Decision {
        data class Accept(val latitude: Double, val longitude: Double, val accuracyM: Double) : Decision()
        data class Reject(val message: String) : Decision()
    }

    fun evaluate(
        latitude: Double?,
        longitude: Double?,
        accuracyM: Double?,
        isMock: Boolean
    ): Decision {
        if (latitude == null || longitude == null || latitude.isNaN() || longitude.isNaN() ||
            !CoordinateValidator.isValidCoordinate(latitude, longitude)
        ) {
            return Decision.Reject("Couldn't get a valid GPS location. Move to an open area and try again.")
        }
        if (isMock) {
            return Decision.Reject("Mock location detected. Turn off any location-spoofing app and try again.")
        }
        if (accuracyM == null || accuracyM.isNaN() || accuracyM < 0.0) {
            return Decision.Reject("GPS accuracy is unavailable. Wait a few seconds and try again.")
        }
        if (accuracyM > MAX_ACCURACY_M) {
            return Decision.Reject(
                "GPS signal is too weak (±${accuracyM.toInt()} m). Move near a window or outdoors and try again."
            )
        }
        return Decision.Accept(latitude, longitude, accuracyM)
    }

    /** Defensive check used by the repository before any new Start/End Day request is sent or queued. */
    fun isSubmittable(latitude: Double, longitude: Double): Boolean =
        !latitude.isNaN() && !longitude.isNaN() && CoordinateValidator.isValidCoordinate(latitude, longitude)
}
