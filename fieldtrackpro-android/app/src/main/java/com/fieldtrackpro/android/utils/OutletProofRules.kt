package com.fieldtrackpro.android.utils

import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/** One GPS fix as seen by the capture screen. [elapsedRealtimeMs] is the fix time on the monotonic clock. */
data class ProofFix(
    val latitude: Double,
    val longitude: Double,
    val accuracyM: Float,
    val elapsedRealtimeMs: Long,
    val isMock: Boolean
)

enum class AccuracyBand { GOOD, FAIR, POOR, NONE }

enum class ShutterBlock { NO_FIX, MOCK_LOCATION, STALE_FIX, ACCURACY_TOO_LOW }

sealed class ShutterState {
    data class Ready(val fix: ProofFix) : ShutterState()
    data class Blocked(val reason: ShutterBlock) : ShutterState()
}

/**
 * Pure client-side mirror of the server's outlet-proof rules (fast feedback only; the server is authoritative).
 * No Android dependencies so it is unit-tested on the JVM.
 */
object OutletProofRules {
    /** Server rejects accuracy above this (OUTLET_PROOF_ACCURACY_TOO_LOW). */
    const val MAX_ACCURACY_M = 30f

    /** Green indicator at or below this. */
    const val GOOD_ACCURACY_M = 20f

    /** The shutter needs a fix at most this old. */
    const val MAX_FIX_AGE_MS = 10_000L

    /** Server: captured_at must be within 180 s of server time. */
    const val SERVER_FRESHNESS_MS = 180_000L

    /** We only attempt a live upload this soon after the click (margin for slow networks / clock skew). */
    const val UPLOAD_SAFE_WINDOW_MS = 150_000L

    const val MAX_PHOTO_BYTES = 10 * 1024 * 1024

    const val MAX_LONG_EDGE_PX = 1600
    const val JPEG_QUALITY = 82

    /** A new-outlet proof (UNATTACHED) is valid for 48 h on the server; stay well under it. */
    const val UNATTACHED_VALID_MS = 47L * 60 * 60 * 1000

    fun band(accuracyM: Float?): AccuracyBand = when {
        accuracyM == null || accuracyM.isNaN() -> AccuracyBand.NONE
        accuracyM <= GOOD_ACCURACY_M -> AccuracyBand.GOOD
        accuracyM <= MAX_ACCURACY_M -> AccuracyBand.FAIR
        else -> AccuracyBand.POOR
    }

    /** Decides whether the shutter may be pressed right now. Priority: no fix, mock, stale, accuracy. */
    fun evaluate(fix: ProofFix?, nowElapsedMs: Long): ShutterState {
        if (fix == null) return ShutterState.Blocked(ShutterBlock.NO_FIX)
        if (fix.isMock) return ShutterState.Blocked(ShutterBlock.MOCK_LOCATION)
        val age = nowElapsedMs - fix.elapsedRealtimeMs
        if (age > MAX_FIX_AGE_MS || age < -1_000L) return ShutterState.Blocked(ShutterBlock.STALE_FIX)
        if (fix.accuracyM.isNaN() || fix.accuracyM > MAX_ACCURACY_M) return ShutterState.Blocked(ShutterBlock.ACCURACY_TOO_LOW)
        return ShutterState.Ready(fix)
    }

    fun blockMessage(reason: ShutterBlock): String = when (reason) {
        ShutterBlock.NO_FIX -> "Waiting for GPS…"
        ShutterBlock.ACCURACY_TOO_LOW -> "Waiting for better GPS…"
        ShutterBlock.STALE_FIX -> "Waiting for a fresh GPS fix…"
        ShutterBlock.MOCK_LOCATION -> "Mock location detected. Turn it off to continue."
    }

    /** ISO-8601 with the device's UTC offset and millisecond precision, e.g. 2026-10-13T16:25:01.123+05:30. */
    fun isoWithOffset(epochMs: Long, zone: ZoneId = ZoneId.systemDefault()): String =
        ISO_FORMAT.format(Instant.ofEpochMilli(epochMs).atZone(zone))

    /**
     * True when a live upload now would still be inside the server's 180 s freshness window (with margin).
     * A capture time in the future beyond clock-skew tolerance is also not uploadable.
     */
    fun isUploadFresh(capturedAtEpochMs: Long?, nowMs: Long): Boolean {
        if (capturedAtEpochMs == null) return false
        val age = nowMs - capturedAtEpochMs
        return age in -30_000L..UPLOAD_SAFE_WINDOW_MS
    }

    /** True while a server-held UNATTACHED proof (new outlet) can still be claimed. */
    fun isUnattachedProofUsable(uploadedAtEpochMs: Long?, nowMs: Long): Boolean =
        uploadedAtEpochMs != null && nowMs - uploadedAtEpochMs in 0..UNATTACHED_VALID_MS

    private val ISO_FORMAT: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSSXXX")
}
