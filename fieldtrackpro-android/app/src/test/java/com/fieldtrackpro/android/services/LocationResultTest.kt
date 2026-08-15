package com.fieldtrackpro.android.services

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * P1-9: LocationResult.isAccuracyAcceptable and ageMillis() are pure
 * functions with no Android framework dependency (no Context, no
 * LocationManager), so they're covered by plain JVM unit tests rather than
 * needing an emulator/instrumented test.
 */
class LocationResultTest {

    private fun result(accuracy: Float, timestamp: Long = 0L) = LocationResult(
        latitude = 12.9716, longitude = 77.5946, accuracy = accuracy, isMockLocation = false, timestamp = timestamp,
    )

    @Test
    fun accuracyAtExactlyTheThreshold_isAcceptable() {
        assertTrue(result(accuracy = LocationCaptureService.MAX_ACCURACY_THRESHOLD_M).isAccuracyAcceptable)
    }

    @Test
    fun accuracyBetterThanTheThreshold_isAcceptable() {
        assertTrue(result(accuracy = 8.0f).isAccuracyAcceptable)
    }

    @Test
    fun accuracyWorseThanTheThreshold_isNotAcceptable() {
        assertFalse(result(accuracy = LocationCaptureService.MAX_ACCURACY_THRESHOLD_M + 0.1f).isAccuracyAcceptable)
    }

    @Test
    fun accuracyFarWorseThanTheThreshold_isNotAcceptable() {
        assertFalse(result(accuracy = 500.0f).isAccuracyAcceptable)
    }

    @Test
    fun ageMillis_reflectsElapsedTimeSinceTheFixWasTaken() {
        val fix = result(accuracy = 5.0f, timestamp = 1_000L)
        assertEquals(4_000L, fix.ageMillis(nowMillis = 5_000L))
    }

    @Test
    fun ageMillis_isZeroForABrandNewFix() {
        val fix = result(accuracy = 5.0f, timestamp = 10_000L)
        assertEquals(0L, fix.ageMillis(nowMillis = 10_000L))
    }
}
