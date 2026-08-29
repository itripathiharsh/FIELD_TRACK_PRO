package com.fieldtrackpro.android

import com.fieldtrackpro.android.utils.CoordinateValidator
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class CoordinateValidationTest {

    private fun isValidCoordinate(latText: String?, lonText: String?): Boolean {
        return CoordinateValidator.isValidCoordinate(latText, lonText)
    }

    @Test
    fun validCoordinates_pass() {
        assertTrue(isValidCoordinate("12.971600", "77.594600"))
    }

    @Test
    fun validCoordinates_boundaryPass() {
        assertTrue(isValidCoordinate("90.0", "180.0"))
        assertTrue(isValidCoordinate("-90.0", "-180.0"))
        assertTrue(isValidCoordinate("0.000001", "0.000001"))
    }

    @Test
    fun nullIsland_rejected() {
        assertFalse(isValidCoordinate("0.0", "0.0"))
        assertFalse(isValidCoordinate("0", "0"))
        assertFalse(isValidCoordinate("0.000000", "0.000000"))
    }

    @Test
    fun zeroLatWithValidLon_accepted() {
        assertTrue("Latitude 0.0 (equator) is valid", isValidCoordinate("0.0", "77.594600"))
    }

    @Test
    fun zeroLonWithValidLat_accepted() {
        assertTrue("Longitude 0.0 (prime meridian) is valid", isValidCoordinate("12.971600", "0.0"))
    }

    @Test
    fun outOfRangeLatitude_rejected() {
        assertFalse(isValidCoordinate("91.0", "77.594600"))
        assertFalse(isValidCoordinate("-91.0", "77.594600"))
    }

    @Test
    fun outOfRangeLongitude_rejected() {
        assertFalse(isValidCoordinate("12.971600", "181.0"))
        assertFalse(isValidCoordinate("12.971600", "-181.0"))
    }

    @Test
    fun nonNumericInput_rejected() {
        assertFalse(isValidCoordinate("abc", "77.594600"))
        assertFalse(isValidCoordinate("12.971600", "xyz"))
        assertFalse(isValidCoordinate("notanumber", "notanumber"))
    }

    @Test
    fun emptyInput_rejected() {
        assertFalse(isValidCoordinate("", "77.594600"))
        assertFalse(isValidCoordinate("12.971600", ""))
        assertFalse(isValidCoordinate("", ""))
    }

    @Test
    fun nullInput_rejected() {
        assertFalse(isValidCoordinate(null, "77.594600"))
        assertFalse(isValidCoordinate("12.971600", null))
        assertFalse(isValidCoordinate(null, null))
    }

    @Test
    fun whitespaceInput_rejected() {
        assertFalse(isValidCoordinate(" ", "77.594600"))
        assertFalse(isValidCoordinate("12.971600", "  "))
    }

    @Test
    fun parseCoordinate_validAndInvalid() {
        assertEquals(12.34, CoordinateValidator.parseCoordinate("12.34")!!, 0.0001)
        assertEquals(-77.5, CoordinateValidator.parseCoordinate(" -77.5 ")!!, 0.0001)
        assertNull(CoordinateValidator.parseCoordinate(""))
        assertNull(CoordinateValidator.parseCoordinate("   "))
        assertNull(CoordinateValidator.parseCoordinate("invalid"))
        assertNull(CoordinateValidator.parseCoordinate(null))
    }
}
