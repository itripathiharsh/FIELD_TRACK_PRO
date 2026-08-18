package com.fieldtrackpro.android.utils

import android.content.Context
import android.content.Intent
import android.net.Uri

/**
 * Helper for navigation to customer locations.
 *
 * Phase 4 Section 4: "navigation is a deep-link handoff to the Google Maps app,
 * not in-app turn-by-turn."
 *
 * Falls back to generic geo: URI if Google Maps app is not installed.
 */
object NavigationHelper {

    /**
     * Open navigation to a customer location.
     *
     * Primary: google.navigation:q=lat,lng (opens Google Maps navigation)
     * Fallback: geo:lat,lng?q=lat,lng(label) (opens any maps app)
     *
     * @param context Android context
     * @param lat Latitude
     * @param lng Longitude
     * @param label Location label (shown in fallback)
     * @return true if navigation was launched, false if no maps app available
     */
    fun navigateToCustomer(context: Context, lat: Double, lng: Double, label: String): Boolean {
        // Validate coordinates before constructing URI
        if (!isValidCoordinate(lat, lng)) {
            return false
        }

        // Primary: Google Maps navigation intent
        val navigationUri = Uri.parse("google.navigation:q=$lat,$lng")
        val navigationIntent = Intent(Intent.ACTION_VIEW, navigationUri).apply {
            setPackage("com.google.android.apps.maps")
        }

        try {
            if (navigationIntent.resolveActivity(context.packageManager) != null) {
                context.startActivity(navigationIntent)
                return true
            }
        } catch (e: Exception) {
            // Fall through
        }

        // Fallback: generic geo: URI
        val fallbackUri = Uri.parse("geo:$lat,$lng?q=$lat,$lng(${Uri.encode(label)})")
        val fallbackIntent = Intent(Intent.ACTION_VIEW, fallbackUri)

        try {
            if (fallbackIntent.resolveActivity(context.packageManager) != null) {
                context.startActivity(fallbackIntent)
                return true
            }
        } catch (e: Exception) {
            // Fall through
        }

        // Final Fallback: Web browser
        try {
            val webUri = Uri.parse("https://maps.google.com/?q=$lat,$lng")
            val webIntent = Intent(Intent.ACTION_VIEW, webUri)
            context.startActivity(webIntent)
            return true
        } catch (e: Exception) {
            return false
        }
    }

    /**
     * Validate that coordinates are within valid ranges and not (0,0).
     */
    fun isValidCoordinate(lat: Double, lng: Double): Boolean {
        if (lat < -90.0 || lat > 90.0) return false
        if (lng < -180.0 || lng > 180.0) return false
        // Reject Null Island
        if (lat == 0.0 && lng == 0.0) return false
        return true
    }

    /**
     * Format coordinates for display.
     */
    fun formatCoordinates(lat: Double, lng: Double): String {
        return "${String.format("%.6f", lat)}, ${String.format("%.6f", lng)}"
    }
}
