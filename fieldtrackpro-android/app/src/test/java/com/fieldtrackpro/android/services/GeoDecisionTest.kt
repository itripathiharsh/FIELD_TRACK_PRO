package com.fieldtrackpro.android.services

import com.fieldtrackpro.android.utils.GeoDecision
import com.fieldtrackpro.android.utils.GeoDecision.Outcome
import com.google.gson.JsonParser
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** Android half of the shared GPS decision vectors (the backend test reads the very same file). */
class GeoDecisionTest {
    private val root = JsonParser.parseReader(
        javaClass.classLoader!!.getResourceAsStream("gps_decision_vectors.json")!!.reader()
    ).asJsonObject

    private fun d(name: String, el: com.google.gson.JsonObject, key: String): Double? =
        el.get(key)?.takeIf { !it.isJsonNull }?.asDouble

    @Test fun constantsMatchTheVectorFile() {
        assertEquals(root["radius_m"].asDouble, 75.0, 0.0)
        assertEquals(root["k"].asDouble, GeoDecision.K, 0.0)
        assertEquals(root["max_accuracy_m"].asDouble, GeoDecision.MAX_ACCURACY_M, 0.0)
        assertEquals(root["live_max_age_s"].asDouble, GeoDecision.LIVE_MAX_AGE_S, 0.0)
    }

    @Test fun everySharedVectorGivesTheSameOutcomeAsTheBackend() {
        val cases = root["cases"].asJsonArray
        assertTrue(cases.size() >= 50)
        for (el in cases) {
            val c = el.asJsonObject
            val name = c["name"].asString
            val result = GeoDecision.decide(
                distanceM = c["distance_m"].asDouble,
                accuracyM = d(name, c, "accuracy_m"),
                pinAccuracyM = d(name, c, "pin_accuracy_m"),
                radiusM = root["radius_m"].asDouble,
                ageS = d(name, c, "age_s"),
                coordsValid = c["coords_valid"].asBoolean
            )
            assertEquals("outcome of $name", c["expected"].asString, result.outcome.name)
            assertEquals("reason of $name", c["reason"]?.takeIf { !it.isJsonNull }?.asString, result.reason)
            assertEquals("point_inside of $name", c["point_inside"].asBoolean, result.pointInside)
        }
    }

    @Test fun reportExamplesForTenFiftySeventyFiveAndHundredMetres() {
        val expect = mapOf(
            10.0 to listOf("INSIDE", "INSIDE", "INSIDE", "INSIDE", "INSIDE"),
            50.0 to listOf("INSIDE", "INSIDE", "INSIDE", "UNCERTAIN", "UNCERTAIN"),
            75.0 to listOf("UNCERTAIN", "UNCERTAIN", "UNCERTAIN", "UNCERTAIN", "UNCERTAIN"),
            100.0 to listOf("OUTSIDE", "OUTSIDE", "UNCERTAIN", "UNCERTAIN", "UNCERTAIN")
        )
        for ((dist, row) in expect) {
            val got = listOf(5.0, 20.0, 40.0, 70.0, 100.0).map {
                GeoDecision.decide(dist, it, null, 75.0, ageS = 1.0).outcome.name
            }
            assertEquals("distance $dist", row, got)
        }
    }

    @Test fun combinedEmployeeAndPinAccuracy() {
        assertEquals(50.0, GeoDecision.combinedUncertainty(40.0, 30.0), 1e-9)
        // d = 55, a = 36: alone 55 + 18 = 73 (inside); with a 30 m pin u = 46.9 -> 78.4 (uncertain)
        assertEquals(Outcome.INSIDE, GeoDecision.decide(55.0, 36.0, null, 75.0, 1.0).outcome)
        assertEquals(Outcome.UNCERTAIN, GeoDecision.decide(55.0, 36.0, 30.0, 75.0, 1.0).outcome)
    }

    @Test fun poorFixesNeverDecide() {
        assertEquals(Outcome.POOR_FIX, GeoDecision.decide(10.0, null, null, 75.0, 1.0).outcome)
        assertEquals(Outcome.POOR_FIX, GeoDecision.decide(10.0, 0.0, null, 75.0, 1.0).outcome)
        assertEquals(Outcome.POOR_FIX, GeoDecision.decide(10.0, Float.MAX_VALUE.toDouble(), null, 75.0, 1.0).outcome)
        assertEquals(Outcome.POOR_FIX, GeoDecision.decide(10.0, 464.0, null, 75.0, 1.0).outcome)
        assertEquals(Outcome.POOR_FIX, GeoDecision.decide(10.0, 10.0, null, 75.0, ageS = 121.0).outcome)
        assertEquals(Outcome.POOR_FIX, GeoDecision.decide(10.0, 10.0, null, 75.0, coordsValid = false).outcome)
        // an offline-queued fix skips only the freshness test
        assertEquals(Outcome.INSIDE, GeoDecision.decide(10.0, 10.0, null, 75.0, ageS = 3 * 3600.0, maxAgeS = null).outcome)
    }
}
