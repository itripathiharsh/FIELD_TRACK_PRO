package com.fieldtrackpro.android.services

import com.fieldtrackpro.android.utils.GeoDecision.Outcome
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FixSelectorTest {
    private val pinLat = 26.7341061
    private val pinLon = 80.9435936
    private val m = 1 / 111_195.0
    private val now = 1_000_000_000L

    private fun fix(metres: Double, acc: Float, ageMs: Long = 1_000L, mock: Boolean = false) =
        LocationResult(pinLat + metres * m, pinLon, acc, mock, now - ageMs)

    private fun selector(pinAcc: Double? = null) = FixSelector(pinLat, pinLon, pinAcc, 75.0)

    @Test fun indoorCoarseFixThenImprovedFix() {
        val s = selector()
        // first delivery: coarse network fix 449 m away with +-464 m -> no decision
        val first = s.offer(fix(449.0, 464f), now)
        assertEquals(Outcome.POOR_FIX, first.decision.outcome)
        assertFalse(first.decidable)
        // two steps later the real fix arrives: +-43 m, 10 m from the outlet -> inside
        val second = s.offer(fix(10.0, 43f), now)
        assertEquals(Outcome.INSIDE, second.decision.outcome)
        assertTrue(second.conclusive)
        assertEquals(43f, s.best!!.fix.accuracy)
        assertEquals(10.0, s.best!!.distanceM, 0.1)
    }

    @Test fun anAccurateFixIsNeverReplacedByAWorseOne() {
        val s = selector()
        s.offer(fix(10.0, 15f), now)
        s.offer(fix(12.0, 60f), now)
        assertEquals(15f, s.best!!.fix.accuracy)
    }

    @Test fun equalAccuracyPrefersTheFresherFix() {
        val s = selector()
        s.offer(fix(10.0, 20f, ageMs = 10_000), now)
        val newer = fix(11.0, 20f, ageMs = 1_000)
        s.offer(newer, now)
        assertEquals(newer.timestamp, s.best!!.fix.timestamp)
    }

    @Test fun staleAndUnknownAccuracyFixesAreNotDecidable() {
        val s = selector()
        assertEquals("STALE", s.offer(fix(10.0, 10f, ageMs = 130_000), now).decision.reason)
        assertEquals("ACCURACY_UNKNOWN", s.offer(fix(10.0, 0f), now).decision.reason)
        assertEquals("ACCURACY_UNKNOWN", s.offer(fix(10.0, Float.MAX_VALUE), now).decision.reason)
        assertFalse(s.best!!.decidable)
    }

    @Test fun uncertainStaysInconclusiveSoCollectionContinues() {
        val s = selector()
        val c = s.offer(fix(60.0, 70f), now)      // 60 + 35 > 75 and 60 - 70 < 75
        assertEquals(Outcome.UNCERTAIN, c.decision.outcome)
        assertFalse(c.conclusive)
        assertTrue(c.decision.pointInside)
    }

    @Test fun outsideIsConclusiveAndReportsTheDistance() {
        val c = selector().offer(fix(500.0, 12f), now)
        assertEquals(Outcome.OUTSIDE, c.decision.outcome)
        assertTrue(c.conclusive)
        assertEquals(500.0, c.distanceM, 1.0)
    }

    @Test fun pinAccuracyMakesTheSelectorMoreCautious() {
        val without = selector().offer(fix(55.0, 36f), now)
        val with = selector(30.0).offer(fix(55.0, 36f), now)
        assertEquals(Outcome.INSIDE, without.decision.outcome)
        assertEquals(Outcome.UNCERTAIN, with.decision.outcome)
    }

    @Test fun invalidCoordinatesAreNotDecidable() {
        val c = selector().offer(LocationResult(0.0, 0.0, 10f, false, now), now)
        assertEquals("INVALID_COORDINATES", c.decision.reason)
    }
}
