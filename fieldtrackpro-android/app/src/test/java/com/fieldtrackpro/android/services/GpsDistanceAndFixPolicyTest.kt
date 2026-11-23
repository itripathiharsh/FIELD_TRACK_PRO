package com.fieldtrackpro.android.services

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Distance maths and fix selection. The expected distances are the SAME numbers the backend test
 * (tests/test_gps_distance_consistency.py) asserts for the same coordinates, so Android and server agree.
 */
class GpsDistanceAndFixPolicyTest {
    private val lat = 26.7341061
    private val lon = 80.9435936

    private fun d(a: Double, b: Double) = LocationCaptureService.calculateDistanceM(lat, lon, a, b)

    @Test fun sameCoordinatesAreZeroMetres() = assertEquals(0.0, d(lat, lon), 0.01)

    @Test fun fewMetresOfMovement() = assertEquals(5.0, d(26.7341511, lon), 0.1)

    @Test fun hundredMetresNorth() = assertEquals(100.0, d(26.7350054, lon), 0.1)

    @Test fun fiveHundredMetresNorth() = assertEquals(500.0, d(26.7386027, lon), 0.5)

    @Test fun hundredMetresEast() = assertEquals(99.77, d(lat, 80.9445982), 0.1)

    @Test fun latitudeLongitudeOrderMatters() {
        // Swapped arguments put the point in another country: thousands of km, never a plausible outlet distance.
        assertTrue(LocationCaptureService.calculateDistanceM(lat, lon, lon, lat) > 1_000_000.0)
    }

    private fun fix(acc: Float, ageMs: Long, now: Long = 1_000_000L) =
        LocationResult(lat, lon, acc, false, now - ageMs) to now

    @Test fun accurateFreshFixIsAccepted() {
        val (f, now) = fix(14.78f, 3_000)
        assertTrue(FixPolicy.isAcceptable(f, nowMillis = now))
    }

    @Test fun coarseNetworkFixIsRejectedEvenWhenFresh() {
        // The device case: first fix +-464 m, then +-43 m. Only the accurate one may be used.
        val (coarse, now) = fix(464f, 1_000)
        assertFalse(FixPolicy.isAcceptable(coarse, nowMillis = now))
        assertTrue(FixPolicy.isAcceptable(fix(43f, 1_000).first, nowMillis = now))
        assertFalse(FixPolicy.isAcceptable(fix(51f, 1_000).first, nowMillis = now))
    }

    @Test fun staleFixIsRejected() {
        val (f, now) = fix(10f, 31_000)
        assertFalse(FixPolicy.isAcceptable(f, nowMillis = now))
    }

    @Test fun unknownAccuracyIsRejected() {
        assertFalse(FixPolicy.accuracyKnown(0f))
        assertFalse(FixPolicy.accuracyKnown(Float.MAX_VALUE))
        assertFalse(FixPolicy.accuracyKnown(Float.NaN))
        assertFalse(FixPolicy.isAcceptable(fix(0f, 1_000).first, nowMillis = 1_000_000L))
    }

    @Test fun betterKeepsTheMoreAccurateFix() {
        val a = fix(464f, 0).first
        val b = fix(43f, 0).first
        assertSame(b, FixPolicy.better(a, b))
        assertSame(b, FixPolicy.better(b, a))
        assertSame(a, FixPolicy.better(null, a))
    }

    @Test fun poorAccuracyMessageTellsTheEmployeeWhatToDo() {
        val msg = FixPolicy.poorAccuracyMessage(fix(464f, 0).first)
        assertTrue(msg.contains("464"))
        assertTrue(msg.contains("open area"))
        assertTrue(msg.contains("50"))
    }
}
