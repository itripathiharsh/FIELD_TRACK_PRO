package com.fieldtrackpro.android.utils

import kotlin.math.sqrt

/**
 * Accuracy-aware geofence decision for check-in. Pure and deterministic.
 *
 * Specification: design-review/gps-checkin-decision-spec.md. The backend has an equivalent function
 * (app/services/geo_decision.py); both are tested against the same vectors (gps_decision_vectors.json).
 */
object GeoDecision {
    const val K = 0.5
    const val MAX_ACCURACY_M = 100.0
    const val LIVE_MAX_AGE_S = 120.0
    const val FUTURE_TOLERANCE_S = 300.0
    const val EPS = 1e-9

    enum class Outcome { INSIDE, OUTSIDE, UNCERTAIN, POOR_FIX }

    data class Result(
        val outcome: Outcome,
        /** Only for POOR_FIX: INVALID_COORDINATES, ACCURACY_UNKNOWN, ACCURACY_TOO_LOW or STALE. */
        val reason: String?,
        val uncertaintyM: Double?,
        /** Point estimate d <= R. */
        val pointInside: Boolean
    )

    private fun known(v: Double?): Boolean = v != null && !v.isNaN() && v > 0.0 && v != Float.MAX_VALUE.toDouble()

    fun combinedUncertainty(accuracyM: Double, pinAccuracyM: Double?): Double =
        if (known(pinAccuracyM)) sqrt(accuracyM * accuracyM + pinAccuracyM!! * pinAccuracyM) else accuracyM

    /** [maxAgeS] = null skips the freshness test (offline-queued check-ins are flagged instead). */
    fun decide(
        distanceM: Double,
        accuracyM: Double?,
        pinAccuracyM: Double?,
        radiusM: Double,
        ageS: Double? = null,
        coordsValid: Boolean = true,
        maxAgeS: Double? = LIVE_MAX_AGE_S
    ): Result {
        val pointInside = distanceM <= radiusM
        if (!coordsValid) return Result(Outcome.POOR_FIX, "INVALID_COORDINATES", null, pointInside)
        if (!known(accuracyM)) return Result(Outcome.POOR_FIX, "ACCURACY_UNKNOWN", null, pointInside)
        val a = accuracyM!!
        if (a > MAX_ACCURACY_M) return Result(Outcome.POOR_FIX, "ACCURACY_TOO_LOW", null, pointInside)
        if (maxAgeS != null && ageS != null && (ageS > maxAgeS || ageS < -FUTURE_TOLERANCE_S)) {
            return Result(Outcome.POOR_FIX, "STALE", null, pointInside)
        }
        val u = combinedUncertainty(a, pinAccuracyM)
        return when {
            distanceM + K * u <= radiusM + EPS -> Result(Outcome.INSIDE, null, u, pointInside)
            distanceM - u > radiusM + EPS -> Result(Outcome.OUTSIDE, null, u, pointInside)
            else -> Result(Outcome.UNCERTAIN, null, u, pointInside)
        }
    }
}
