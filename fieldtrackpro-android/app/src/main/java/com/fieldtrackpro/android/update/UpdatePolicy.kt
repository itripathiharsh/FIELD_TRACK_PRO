package com.fieldtrackpro.android.update

/**
 * Pure decision logic for in-app updates (unit tested).
 *
 * - Never offers a downgrade or a reinstall of the same version (versionCode must be strictly greater).
 * - Mandatory when the manifest says so OR the installed version is below minSupportedVersionCode.
 *   A mandatory update cannot be snoozed.
 * - "Later" on an optional update hides it for [SNOOZE_MS] for THAT version only; a newer version is offered
 *   immediately. A third "Later" on the same version stretches the reminder to [LONG_SNOOZE_MS].
 */
object UpdatePolicy {

    const val SNOOZE_MS = 24L * 60 * 60 * 1000          // remind again after a day
    const val LONG_SNOOZE_MS = 3L * 24 * 60 * 60 * 1000 // after the 3rd "Later" for the same version
    const val MIN_CHECK_INTERVAL_MS = 60L * 60 * 1000   // at most one network check per hour while the app is used

    sealed class Decision {
        object UpToDate : Decision()
        data class Optional(val manifest: UpdateManifest) : Decision()
        data class Mandatory(val manifest: UpdateManifest, val reason: String) : Decision()
        /** An optional update exists but the user chose "Later" recently. */
        data class Snoozed(val manifest: UpdateManifest, val untilMs: Long) : Decision()
        data class Ignored(val reason: String) : Decision()
    }

    data class SnoozeState(val versionCode: Long = 0, val untilMs: Long = 0, val count: Int = 0)

    fun decide(
        installedVersionCode: Long,
        manifest: UpdateManifest?,
        expectedPackage: String,
        allowedHosts: Set<String>,
        snooze: SnoozeState,
        nowMs: Long
    ): Decision {
        if (manifest == null) return Decision.Ignored("No manifest")
        manifest.problem(expectedPackage, allowedHosts)?.let { return Decision.Ignored(it) }
        if (manifest.versionCode <= installedVersionCode) return Decision.UpToDate

        val belowMinimum = installedVersionCode < manifest.minSupportedVersionCode
        if (manifest.mandatory || belowMinimum) {
            val reason = if (belowMinimum) {
                "This version of FieldTrack Pro is no longer supported."
            } else {
                "This update is required to keep using FieldTrack Pro."
            }
            return Decision.Mandatory(manifest, reason)
        }
        if (snooze.versionCode == manifest.versionCode && nowMs < snooze.untilMs) {
            return Decision.Snoozed(manifest, snooze.untilMs)
        }
        return Decision.Optional(manifest)
    }

    /** New snooze state after the user taps "Later" on [versionCode]. */
    fun snoozeAfterLater(previous: SnoozeState, versionCode: Long, nowMs: Long): SnoozeState {
        val count = if (previous.versionCode == versionCode) previous.count + 1 else 1
        val duration = if (count >= 3) LONG_SNOOZE_MS else SNOOZE_MS
        return SnoozeState(versionCode = versionCode, untilMs = nowMs + duration, count = count)
    }

    fun shouldCheckNow(lastCheckMs: Long, nowMs: Long, coldStart: Boolean): Boolean =
        coldStart || lastCheckMs <= 0 || nowMs - lastCheckMs >= MIN_CHECK_INTERVAL_MS || nowMs < lastCheckMs
}
