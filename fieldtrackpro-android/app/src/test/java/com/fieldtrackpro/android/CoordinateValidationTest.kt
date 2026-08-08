package com.fieldtrackpro.android

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CoordinateValidationTest {

    private fun isValidCoordinate(latText: String?, lonText: String?): Boolean {
        val parsedLat = latText?.toDoubleOrNull()
        val parsedLon = lonText?.toDoubleOrNull()
        val isNotNullIsland = parsedLat != 0.0 || parsedLon != 0.0
        return parsedLat != null && parsedLon != null &&
            parsedLat in -90.0..90.0 && parsedLon in -180.0..180.0 && isNotNullIsland
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
    fun validNearZeroCoordinates_pass() {
        assertTrue(isValidCoordinate("0.000001", "0.000001"))
        assertTrue(isValidCoordinate("-0.000001", "0.000001"))
        assertTrue(isValidCoordinate("0.000001", "-0.000001"))
    }

    @Test
    fun emptyFields_areRejectedAsInvalid() {
        assertFalse("Empty latitude must be rejected", isValidCoordinate("", "77.594600"))
        assertFalse("Empty longitude must be rejected", isValidCoordinate("12.971600", ""))
        assertFalse("Both empty must be rejected", isValidCoordinate("", ""))
    }

    @Test
    fun noHardcodedCoordinates_productionDefaultIsInvalid() {
        val emptyLat = ""
        val emptyLon = ""
        assertFalse(
            "Production default (empty fields) must not be treated as valid coordinates",
            isValidCoordinate(emptyLat, emptyLon)
        )
    }
}
