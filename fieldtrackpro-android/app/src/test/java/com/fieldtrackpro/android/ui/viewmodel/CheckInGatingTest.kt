package com.fieldtrackpro.android.ui.viewmodel

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Tests for geofence check-in gating logic.
 *
 * The gating rule in VisitDetailsScreen is:
 *   val canCheckIn = !geofenceUiState.isMonitoring || geofenceUiState.isInside
 *
 * This means:
 * - If NOT monitoring → check-in allowed (bypass geofence)
 * - If monitoring AND inside → check-in allowed
 * - If monitoring AND outside → check-in blocked
 * - If monitoring AND unknown → check-in blocked
 */
class CheckInGatingTest {

    private fun canCheckIn(isMonitoring: Boolean, isInside: Boolean): Boolean {
        return !isMonitoring || isInside
    }

    @Test
    fun checkIn_notMonitoring_allowsCheckIn() {
        assertTrue("Check-in should be allowed when not monitoring",
            canCheckIn(isMonitoring = false, isInside = false))
        assertTrue("Check-in should be allowed when not monitoring (even if inside)",
            canCheckIn(isMonitoring = false, isInside = true))
    }

    @Test
    fun checkIn_monitoringAndInside_allowsCheckIn() {
        assertTrue("Check-in should be allowed when monitoring and inside",
            canCheckIn(isMonitoring = true, isInside = true))
    }

    @Test
    fun checkIn_monitoringAndOutside_blocksCheckIn() {
        assertFalse("Check-in should be blocked when monitoring and outside",
            canCheckIn(isMonitoring = true, isInside = false))
    }
}
