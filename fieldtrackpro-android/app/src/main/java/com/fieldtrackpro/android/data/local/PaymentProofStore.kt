package com.fieldtrackpro.android.data.local

import android.content.Context
import android.net.Uri
import com.fieldtrackpro.android.utils.ImageDownsampler
import java.io.File
import java.util.UUID

/** Copies proof photos into app-private storage so queued payments keep their proofs until they sync. */
object PaymentProofStore {
    private const val DIR = "payment_proofs"

    /** Backend caps proof images at 10 MB (a larger file is rejected permanently): always downsample first. */
    const val PROOF_MAX_DIMENSION_PX = 1600
    const val PROOF_JPEG_QUALITY = 82

    /**
     * Copies the photo into app-private storage, DOWNSAMPLED to at most [PROOF_MAX_DIMENSION_PX] px (long edge) and
     * re-encoded as JPEG q[PROOF_JPEG_QUALITY] (EXIF rotation applied). A full-resolution camera JPEG could exceed the
     * backend's 10 MB limit and be rejected for good. If the image cannot be decoded at all the raw bytes are copied
     * unchanged (the queue processor then keeps the file as a conflict if the server refuses it as too large).
     * Returns the absolute private path, or null if the source cannot be read.
     */
    fun copyToPrivate(context: Context, source: Uri): String? = try {
        val dir = File(context.filesDir, DIR).also { it.mkdirs() }
        val target = File(dir, "proof_${UUID.randomUUID()}.jpg")
        val downsampled = try {
            ImageDownsampler.downsample(context, source, PROOF_MAX_DIMENSION_PX, PROOF_JPEG_QUALITY)
        } catch (e: Exception) {
            null
        } catch (e: OutOfMemoryError) {
            null
        }
        if (downsampled != null && downsampled.isNotEmpty()) {
            target.outputStream().use { it.write(downsampled) }
        } else {
            val input = context.contentResolver.openInputStream(source)
            if (input != null) {
                input.use { ins -> target.outputStream().use { out -> ins.copyTo(out) } }
            }
        }
        if (target.length() > 0) target.absolutePath else { target.delete(); null }
    } catch (e: Exception) {
        null
    }

    fun delete(path: String) {
        try { File(path).delete() } catch (_: Exception) {}
    }

    /** Orphans older than this are safe to assume abandoned (capture started, submit never happened). */
    private val ORPHAN_AGE_MS = java.util.concurrent.TimeUnit.HOURS.toMillis(24)

    /**
     * Deletes proof files that are neither referenced by any currently-queued payment NOR
     * recent enough to still be mid-capture.
     *
     * copyToPrivate() and the offline-queue entry that references its path are two separate
     * writes with nothing tying them together: if the app is killed in between (photo taken,
     * app closed before tapping Submit), the file is orphaned - not deleted, not queued, not
     * referenced by anything. This does not recover that photo (there is nothing to recover; the
     * payment was never submitted), it only bounds how long the leaked file sits on disk.
     */
    fun pruneOrphaned(context: Context, referencedPaths: Set<String>, maxAgeMs: Long = ORPHAN_AGE_MS) {
        try {
            val dir = File(context.filesDir, DIR)
            val files = dir.listFiles() ?: return
            val cutoff = System.currentTimeMillis() - maxAgeMs
            for (f in files) {
                if (f.absolutePath !in referencedPaths && f.lastModified() < cutoff) {
                    f.delete()
                }
            }
        } catch (_: Exception) {
            // Best-effort housekeeping; never fail the caller over this.
        }
    }
}
