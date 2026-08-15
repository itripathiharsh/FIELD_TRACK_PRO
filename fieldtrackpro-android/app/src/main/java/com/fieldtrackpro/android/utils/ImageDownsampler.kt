package com.fieldtrackpro.android.utils

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.media.ExifInterface
import android.net.Uri
import java.io.ByteArrayOutputStream

/**
 * P1-10: downsamples and compresses a picked/captured photo before upload.
 *
 * Previously the upload path read a picker/camera Uri's bytes directly with
 * `contentResolver.openInputStream(uri).readBytes()` - a full-resolution
 * modern camera photo (12MP+, often 4000x3000) loaded entirely into memory
 * with no resizing at all, the textbook Android OOM pattern, then uploaded
 * as-is (often several MB over a poor field connection).
 *
 * Chosen limits, and why:
 *  - MAX_DIMENSION_PX = 1600: this app's photos are evidence/documentation
 *    (outlet visits, signed order notes, payment proofs) viewed on a phone
 *    screen or in an admin review list/PDF export - not large-format prints.
 *    1600px on the long edge is comfortably more detail than any of those
 *    consumption paths can show, while cutting a typical 4000x3000 (12MP)
 *    photo to roughly a tenth of its original pixel count and file size.
 *  - JPEG_QUALITY = 85: the standard "visually near-lossless, meaningfully
 *    smaller" compression point for photographic content; below ~80 JPEG
 *    artifacts start being visible on text/receipts, which this app
 *    frequently photographs as evidence.
 * These are engineering defaults addressing a real memory/bandwidth problem,
 * not an invented business requirement about photo quality - see the P1
 * report for the corresponding product-decision note if a different
 * standard is wanted.
 */
object ImageDownsampler {

    const val MAX_DIMENSION_PX = 1600
    const val JPEG_QUALITY = 85

    /**
     * Reads [uri] efficiently (bounds-only decode first, per Android's own
     * guidance for avoiding OOM on large bitmaps), downsamples to at most
     * [MAX_DIMENSION_PX] on the long edge, corrects EXIF rotation, and
     * re-encodes as JPEG. Returns null if the URI cannot be read/decoded as
     * an image at all (caller falls back to the original bytes/behaviour).
     */
    fun downsample(context: Context, uri: Uri): ByteArray? {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        context.contentResolver.openInputStream(uri)?.use {
            BitmapFactory.decodeStream(it, null, bounds)
        } ?: return null

        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null

        val sampleSize = calculateInSampleSize(bounds.outWidth, bounds.outHeight, MAX_DIMENSION_PX)
        val decodeOptions = BitmapFactory.Options().apply { inSampleSize = sampleSize }
        val sampled = context.contentResolver.openInputStream(uri)?.use {
            BitmapFactory.decodeStream(it, null, decodeOptions)
        } ?: return null

        val rotationDegrees = readExifRotationDegrees(context, uri)
        val rotated = if (rotationDegrees != 0) {
            val matrix = Matrix().apply { postRotate(rotationDegrees.toFloat()) }
            val result = Bitmap.createBitmap(sampled, 0, 0, sampled.width, sampled.height, matrix, true)
            if (result !== sampled) sampled.recycle()
            result
        } else {
            sampled
        }

        // A downsampled 1600px-long-edge bitmap can still exceed
        // MAX_DIMENSION_PX on the short edge's opposite case (inSampleSize is
        // a power of two, so it can overshoot) - clamp with one more scale
        // pass if needed.
        val longEdge = maxOf(rotated.width, rotated.height)
        val finalBitmap = if (longEdge > MAX_DIMENSION_PX) {
            val scale = MAX_DIMENSION_PX.toFloat() / longEdge
            val scaled = Bitmap.createScaledBitmap(
                rotated, (rotated.width * scale).toInt().coerceAtLeast(1),
                (rotated.height * scale).toInt().coerceAtLeast(1), true,
            )
            if (scaled !== rotated) rotated.recycle()
            scaled
        } else {
            rotated
        }

        return try {
            ByteArrayOutputStream().use { out ->
                finalBitmap.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, out)
                out.toByteArray()
            }
        } finally {
            finalBitmap.recycle()
        }
    }

    /**
     * P1-10 (preview/download side): the same OOM pattern exists when
     * viewing a downloaded photo - `BitmapFactory.decodeByteArray(bytes, 0,
     * bytes.size)` with no inSampleSize decodes at full resolution even
     * though the result is only ever displayed at screen size. Bounds-only
     * decode first, then a sampled decode - never allocates a full-res
     * bitmap just to immediately scale it down for display.
     */
    fun decodeSampledBitmapForDisplay(bytes: ByteArray, maxDimension: Int = MAX_DIMENSION_PX): Bitmap? {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null

        val decodeOptions = BitmapFactory.Options().apply {
            inSampleSize = calculateInSampleSize(bounds.outWidth, bounds.outHeight, maxDimension)
        }
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.size, decodeOptions)
    }

    /** Android's own recommended power-of-two inSampleSize calculation (avoids decoding full-resolution pixel data just to immediately downscale it). */
    fun calculateInSampleSize(rawWidth: Int, rawHeight: Int, maxDimension: Int): Int {
        var inSampleSize = 1
        var width = rawWidth
        var height = rawHeight
        while (width / 2 >= maxDimension || height / 2 >= maxDimension) {
            width /= 2
            height /= 2
            inSampleSize *= 2
        }
        return inSampleSize
    }

    private fun readExifRotationDegrees(context: Context, uri: Uri): Int {
        return try {
            context.contentResolver.openInputStream(uri)?.use { stream ->
                val exif = ExifInterface(stream)
                when (exif.getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)) {
                    ExifInterface.ORIENTATION_ROTATE_90 -> 90
                    ExifInterface.ORIENTATION_ROTATE_180 -> 180
                    ExifInterface.ORIENTATION_ROTATE_270 -> 270
                    else -> 0
                }
            } ?: 0
        } catch (e: Exception) {
            0
        }
    }
}
