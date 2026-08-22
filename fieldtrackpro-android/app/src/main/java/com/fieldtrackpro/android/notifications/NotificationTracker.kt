package com.fieldtrackpro.android.notifications

import android.content.Context
import android.content.SharedPreferences

/**
 * Thread-safe deduplication tracker for notifications.
 *
 * Ensures that notifications delivered via real-time FCM push notifications
 * are never duplicated by the fallback polling NotificationSyncWorker, and vice-versa.
 */
object NotificationTracker {
    private const val PREFS_NOTIF_TRACKER = "fieldtrack_notif_tracker"
    private const val KEY_DELIVERED_IDS = "delivered_notif_ids"
    private const val MAX_TRACKED_IDS = 500

    @Volatile
    internal var testPreferences: SharedPreferences? = null

    private fun getPrefs(context: Context?): SharedPreferences {
        testPreferences?.let { return it }
        requireNotNull(context) { "Context must not be null when testPreferences is not set" }
        return context.getSharedPreferences(PREFS_NOTIF_TRACKER, Context.MODE_PRIVATE)
    }

    @Synchronized
    fun isDelivered(context: Context?, notificationId: String): Boolean {
        if (notificationId.isBlank()) return false
        val prefs = getPrefs(context)
        val deliveredIds = prefs.getStringSet(KEY_DELIVERED_IDS, emptySet()) ?: emptySet()
        return deliveredIds.contains(notificationId)
    }

    @Synchronized
    fun markDelivered(context: Context?, notificationId: String) {
        if (notificationId.isBlank()) return
        val prefs = getPrefs(context)
        val deliveredIds = prefs.getStringSet(KEY_DELIVERED_IDS, emptySet())?.toMutableSet() ?: mutableSetOf()
        deliveredIds.add(notificationId)

        if (deliveredIds.size > MAX_TRACKED_IDS) {
            val trimmed = deliveredIds.toList().takeLast(MAX_TRACKED_IDS / 2).toSet()
            prefs.edit().putStringSet(KEY_DELIVERED_IDS, trimmed).apply()
        } else {
            prefs.edit().putStringSet(KEY_DELIVERED_IDS, deliveredIds).apply()
        }
    }

    @Synchronized
    fun markDelivered(context: Context?, notificationIds: Collection<String>) {
        if (notificationIds.isEmpty()) return
        val prefs = getPrefs(context)
        val deliveredIds = prefs.getStringSet(KEY_DELIVERED_IDS, emptySet())?.toMutableSet() ?: mutableSetOf()
        deliveredIds.addAll(notificationIds.filter { it.isNotBlank() })

        if (deliveredIds.size > MAX_TRACKED_IDS) {
            val trimmed = deliveredIds.toList().takeLast(MAX_TRACKED_IDS / 2).toSet()
            prefs.edit().putStringSet(KEY_DELIVERED_IDS, trimmed).apply()
        } else {
            prefs.edit().putStringSet(KEY_DELIVERED_IDS, deliveredIds).apply()
        }
    }

    @Synchronized
    fun clear(context: Context?) {
        val prefs = getPrefs(context)
        prefs.edit().remove(KEY_DELIVERED_IDS).apply()
    }
}
