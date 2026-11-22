package com.fieldtrackpro.android.update

import android.content.SharedPreferences

/**
 * Persists the last valid manifest (so a MANDATORY update still applies after a restart while offline: it cannot be
 * bypassed by turning the network off), the snooze state and the last check time. Nothing here is sensitive.
 */
class UpdateStore(private val prefs: SharedPreferences) {

    fun lastManifestJson(): String? = prefs.getString(KEY_MANIFEST, null)

    fun saveManifestJson(json: String) {
        prefs.edit().putString(KEY_MANIFEST, json).apply()
    }

    fun snooze(): UpdatePolicy.SnoozeState = UpdatePolicy.SnoozeState(
        versionCode = prefs.getLong(KEY_SNOOZE_VERSION, 0),
        untilMs = prefs.getLong(KEY_SNOOZE_UNTIL, 0),
        count = prefs.getInt(KEY_SNOOZE_COUNT, 0)
    )

    fun saveSnooze(state: UpdatePolicy.SnoozeState) {
        prefs.edit()
            .putLong(KEY_SNOOZE_VERSION, state.versionCode)
            .putLong(KEY_SNOOZE_UNTIL, state.untilMs)
            .putInt(KEY_SNOOZE_COUNT, state.count)
            .apply()
    }

    fun lastCheckMs(): Long = prefs.getLong(KEY_LAST_CHECK, 0)

    fun saveLastCheckMs(value: Long) {
        prefs.edit().putLong(KEY_LAST_CHECK, value).apply()
    }

    companion object {
        const val PREFS_NAME = "fieldtrack_app_update"
        private const val KEY_MANIFEST = "last_manifest_json"
        private const val KEY_SNOOZE_VERSION = "snooze_version_code"
        private const val KEY_SNOOZE_UNTIL = "snooze_until_ms"
        private const val KEY_SNOOZE_COUNT = "snooze_count"
        private const val KEY_LAST_CHECK = "last_check_ms"
    }
}
