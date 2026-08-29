package com.fieldtrackpro.android.services

import com.fieldtrackpro.android.ui.viewmodel.GeofenceUiState
import com.fieldtrackpro.android.ui.viewmodel.GeofenceUiStatus
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Unit tests for Attendance GPS freshness, Geofence gating state machine, and Haversine math.
 *
 * Covers:
 * - APP-ATT-001: GPS freshness <= 30 seconds
 * - APP-ATT-005: Geofence gating state machine
 * - APP-ATT-008: Distance calculation consistency
 */
class LocationFreshnessAndGatingTest {

    @Test
    fun fixUnder30Seconds_isConsideredFresh() {
        val now = System.currentTimeMillis()
        val fix = LocationResult(
            latitude = 12.9716,
            longitude = 77.5946,
            accuracy = 10.0f,
            isMockLocation = false,
            timestamp = now - 15_000L // 15 seconds old
        )
        assertTrue(fix.ageMillis(now) <= LocationCaptureService.MAX_FRESHNESS_MS)
    }

    @Test
    fun fixOver30Seconds_isConsideredStale() {
        val now = System.currentTimeMillis()
        val fix = LocationResult(
            latitude = 12.9716,
            longitude = 77.5946,
            accuracy = 10.0f,
            isMockLocation = false,
            timestamp = now - 35_000L // 35 seconds old
        )
        assertFalse(fix.ageMillis(now) <= LocationCaptureService.MAX_FRESHNESS_MS)
    }

    @Test
    fun geofenceGating_canProceedOnlyWhenMonitoringAndInside() {
        // Unknown / Locating
        val locatingState = GeofenceUiState(
            isMonitoring = false,
            isLoadingLocation = true,
            status = GeofenceUiStatus.LOCATING
        )
        assertFalse(locatingState.canProceedToCheckIn)

        // Outside radius
        val outsideState = GeofenceUiState(
            isMonitoring = true,
            isInside = false,
            isOutside = true,
            hasPermission = true,
            isLocationEnabled = true,
            status = GeofenceUiStatus.OUTSIDE
        )
        assertFalse(outsideState.canProceedToCheckIn)

        // Monitoring + Inside + Permission + Enabled
        val insideState = GeofenceUiState(
            isMonitoring = true,
            isInside = true,
            isOutside = false,
            hasPermission = true,
            isLocationEnabled = true,
            isLoadingLocation = false,
            status = GeofenceUiStatus.INSIDE
        )
        assertTrue(insideState.canProceedToCheckIn)
    }

    @Test
    fun haversineDistance_samePointIsZero() {
        val d = LocationCaptureService.calculateDistanceM(12.9716, 77.5946, 12.9716, 77.5946)
        assertEquals(0.0, d, 0.01)
    }

    @Test
    fun haversineDistance_knownProximity() {
        val d = LocationCaptureService.calculateDistanceM(12.9716, 77.5946, 12.9720, 77.5946)
        assertTrue(d in 40.0..50.0)
    }
}
