package com.fieldtrackpro.android.data.local

import android.content.Context
import java.io.File
import java.util.UUID
import java.util.concurrent.TimeUnit

/**
 * App-private storage for outlet proof photos (filesDir/outlet_proofs). Never the gallery / shared storage.
 * Mirrors [PaymentProofStore].
 */
object OutletProofStore {
    const val DIR = "outlet_proofs"

    /** Files older than this and referenced by nothing are abandoned captures and are swept. */
    val ORPHAN_AGE_MS: Long = TimeUnit.DAYS.toMillis(7)

    fun dir(context: Context): File = File(context.filesDir, DIR).also { it.mkdirs() }

    /** A new, not-yet-existing file for [prefix] ("raw" camera output or the final "proof" JPEG). */
    fun newFile(context: Context, prefix: String): File = File(dir(context), "${prefix}_${UUID.randomUUID()}.jpg")

    fun delete(path: String?) {
        if (path.isNullOrBlank()) return
        try { File(path).delete() } catch (_: Exception) {}
    }

    /**
     * Deletes files in [dir] that are not in [referencedPaths] and were last modified before
     * now - [maxAgeMs]. Returns how many were deleted. Pure on purpose (unit-tested with a temp dir).
     */
    fun pruneOrphanedIn(
        dir: File,
        referencedPaths: Set<String>,
        nowMs: Long = System.currentTimeMillis(),
        maxAgeMs: Long = ORPHAN_AGE_MS
    ): Int {
        var deleted = 0
        try {
            val files = dir.listFiles() ?: return 0
            val cutoff = nowMs - maxAgeMs
            for (f in files) {
                if (f.isFile && f.absolutePath !in referencedPaths && f.lastModified() < cutoff) {
                    if (f.delete()) deleted++
                }
            }
        } catch (_: Exception) {
            // Best-effort housekeeping; never fail the caller over this.
        }
        return deleted
    }

    fun pruneOrphaned(context: Context, referencedPaths: Set<String>): Int =
        pruneOrphanedIn(File(context.filesDir, DIR), referencedPaths)
}
