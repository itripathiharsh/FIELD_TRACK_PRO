package com.fieldtrackpro.android

import com.fieldtrackpro.android.utils.NavigationHelper
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NavigationHelperTest {

    @Test
    fun validCoordinates_pass() {
        assertTrue(NavigationHelper.isValidCoordinate(12.9716, 77.5946))
        assertTrue(NavigationHelper.isValidCoordinate(0.0001, 0.0001))
        assertTrue(NavigationHelper.isValidCoordinate(-90.0, -180.0))
        assertTrue(NavigationHelper.isValidCoordinate(90.0, 180.0))
    }

    @Test
    fun nullIsland_rejected() {
        assertFalse("Null Island should be rejected", NavigationHelper.isValidCoordinate(0.0, 0.0))
    }

    @Test
    fun outOfRangeLatitude_rejected() {
        assertFalse(NavigationHelper.isValidCoordinate(91.0, 77.5946))
        assertFalse(NavigationHelper.isValidCoordinate(-91.0, 77.5946))
    }

    @Test
    fun outOfRangeLongitude_rejected() {
        assertFalse(NavigationHelper.isValidCoordinate(12.9716, 181.0))
        assertFalse(NavigationHelper.isValidCoordinate(12.9716, -181.0))
    }

    @Test
    fun formatCoordinates_correctFormat() {
        val formatted = NavigationHelper.formatCoordinates(12.9716, 77.5946)
        assertEquals("12.971600, 77.594600", formatted)
    }

    @Test
    fun formatCoordinates_negativeValues() {
        val formatted = NavigationHelper.formatCoordinates(-33.8688, 151.2093)
        assertEquals("-33.868800, 151.209300", formatted)
    }
}
