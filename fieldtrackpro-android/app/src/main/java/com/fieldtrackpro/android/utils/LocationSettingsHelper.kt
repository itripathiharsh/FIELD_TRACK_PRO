package com.fieldtrackpro.android.utils

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings

/**
 * Utility for opening system settings for location services and app permissions.
 */
object LocationSettingsHelper {

    /**
     * Opens Android system Location Settings where the user can enable device Location/GPS.
     * Uses [Settings.ACTION_LOCATION_SOURCE_SETTINGS].
     */
    fun openLocationSettings(context: Context) {
        val intent = Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
        }
        try {
            context.startActivity(intent)
        } catch (e: Exception) {
            // Fallback to generic system settings if specific intent is not supported
            try {
                val fallbackIntent = Intent(Settings.ACTION_SETTINGS).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                context.startActivity(fallbackIntent)
            } catch (ignored: Exception) {
            }
        }
    }

    /**
     * Opens Application Details Settings where the user can grant permanently denied permissions.
     * Uses [Settings.ACTION_APPLICATION_DETAILS_SETTINGS].
     */
    fun openAppSettings(context: Context) {
        val intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
            data = Uri.fromParts("package", context.packageName, null)
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
        }
        try {
            context.startActivity(intent)
        } catch (e: Exception) {
            try {
                val fallbackIntent = Intent(Settings.ACTION_SETTINGS).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                context.startActivity(fallbackIntent)
            } catch (ignored: Exception) {
            }
        }
    }
}
