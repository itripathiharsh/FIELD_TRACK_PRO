package com.fieldtrackpro.android.utils

/**
 * Coordinate validator utility for GPS coordinates.
 *
 * APP-ATT-004: Standardizes latitude (-90..90) and longitude (-180..180) checks.
 * Rejects (0.0, 0.0) as invalid/null island fallback while accepting legitimate
 * coordinates anywhere in the world.
 */
object CoordinateValidator {

    fun isValidCoordinate(latText: String?, lonText: String?): Boolean {
        val parsedLat = parseCoordinate(latText)
        val parsedLon = parseCoordinate(lonText)
        return isValidCoordinate(parsedLat, parsedLon)
    }

    fun isValidCoordinate(latitude: Double?, longitude: Double?): Boolean {
        if (latitude == null || longitude == null) return false
        val isNotNullIsland = latitude != 0.0 || longitude != 0.0
        return latitude in -90.0..90.0 && longitude in -180.0..180.0 && isNotNullIsland
    }

    fun parseCoordinate(text: String?): Double? {
        val trimmed = text?.trim() ?: return null
        if (trimmed.isEmpty()) return null
        val parsed = trimmed.toDoubleOrNull() ?: return null
        return if (parsed.isNaN() || parsed.isInfinite()) null else parsed
    }
}
