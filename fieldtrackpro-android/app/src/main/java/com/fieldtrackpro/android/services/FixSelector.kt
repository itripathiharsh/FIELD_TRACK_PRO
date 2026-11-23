package com.fieldtrackpro.android.services

import com.fieldtrackpro.android.utils.CoordinateValidator
import com.fieldtrackpro.android.utils.GeoDecision

/**
 * Chooses the best fix while fresh location updates arrive for a check-in. Pure (no Android types) so the "indoor coarse
 * fix followed by an improved one" behaviour is unit-tested on the JVM.
 *
 * "Best" = a fix that can be decided on (not POOR_FIX) beats one that cannot; among decidable fixes the more accurate
 * wins, and for equal accuracy the fresher one.
 */
class FixSelector(
    private val pinLat: Double,
    private val pinLon: Double,
    private val pinAccuracyM: Double?,
    private val radiusM: Double
) {
    data class Candidate(
        val fix: LocationResult,
        val distanceM: Double,
        val decision: GeoDecision.Result,
        val ageS: Double
    ) {
        val decidable: Boolean get() = decision.outcome != GeoDecision.Outcome.POOR_FIX
        val conclusive: Boolean
            get() = decision.outcome == GeoDecision.Outcome.INSIDE || decision.outcome == GeoDecision.Outcome.OUTSIDE
    }

    var best: Candidate? = null
        private set
    var latest: Candidate? = null
        private set

    fun offer(fix: LocationResult, nowMillis: Long = System.currentTimeMillis()): Candidate {
        val coordsValid = CoordinateValidator.isValidCoordinate(fix.latitude, fix.longitude)
        val distance = if (coordsValid) {
            LocationCaptureService.calculateDistanceM(fix.latitude, fix.longitude, pinLat, pinLon)
        } else 0.0
        val ageS = fix.ageMillis(nowMillis) / 1000.0
        val decision = GeoDecision.decide(
            distanceM = distance,
            accuracyM = fix.accuracy.toDouble(),
            pinAccuracyM = pinAccuracyM,
            radiusM = radiusM,
            ageS = ageS,
            coordsValid = coordsValid
        )
        val candidate = Candidate(fix, distance, decision, ageS)
        latest = candidate
        if (isBetter(candidate, best)) best = candidate
        return candidate
    }

    private fun isBetter(c: Candidate, current: Candidate?): Boolean {
        if (current == null) return true
        if (c.decidable != current.decidable) return c.decidable
        if (c.fix.accuracy != current.fix.accuracy) return c.fix.accuracy < current.fix.accuracy
        return c.fix.timestamp > current.fix.timestamp
    }
}
