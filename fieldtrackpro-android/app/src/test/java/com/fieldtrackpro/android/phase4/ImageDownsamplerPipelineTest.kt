package com.fieldtrackpro.android.phase4

import android.app.Application
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.media.ExifInterface
import android.net.Uri
import androidx.test.core.app.ApplicationProvider
import com.fieldtrackpro.android.utils.ImageDownsampler
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.File
import java.io.FileOutputStream

/**
 * Regression test for the camera failure "The photo could not be processed. Please try again."
 *
 * Root cause: ImageDownsampler.downsample() did the bounds-only decode as
 *     openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, bounds) } ?: return null
 * With inJustDecodeBounds = true, decodeStream() ALWAYS returns null (it only fills `bounds`), so the elvis operator
 * returned null for every photo. The outlet-proof capture treats null as "could not be processed". (Payment/visit
 * uploads silently fell back to the un-downsampled original, so the bug was invisible there.)
 */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34], application = Application::class)
class ImageDownsamplerPipelineTest {
    private val context: Application = ApplicationProvider.getApplicationContext()

    private fun jpeg(w: Int, h: Int, exifOrientation: Int? = null): File {
        val bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        val c = Canvas(bmp)
        c.drawColor(Color.rgb(30, 60, 120))
        c.drawRect(0f, 0f, w / 2f, h / 2f, Paint().apply { color = Color.rgb(250, 160, 20) })
        val f = File.createTempFile("cam", ".jpg", context.cacheDir)
        FileOutputStream(f).use { bmp.compress(Bitmap.CompressFormat.JPEG, 90, it) }
        bmp.recycle()
        if (exifOrientation != null) {
            ExifInterface(f.absolutePath).apply {
                setAttribute(ExifInterface.TAG_ORIENTATION, exifOrientation.toString())
                saveAttributes()
            }
        }
        return f
    }

    private fun dims(bytes: ByteArray): Pair<Int, Int> {
        val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, o)
        return o.outWidth to o.outHeight
    }

    @Test fun aNormalCameraPhotoIsProcessed() {
        val f = jpeg(4000, 3000)
        val out = ImageDownsampler.downsample(context, Uri.fromFile(f), 1600, 82)
        assertNotNull("downsample() returned null for a valid JPEG (this was the camera bug)", out)
        val (w, h) = dims(out!!)
        assertTrue("long edge must be <= 1600, was ${maxOf(w, h)}", maxOf(w, h) <= 1600)
        assertTrue("image must not be empty", out.size > 1000)
    }

    @Test fun smallPhotosAreKeptAtTheirSize() {
        val f = jpeg(800, 600)
        val (w, h) = dims(ImageDownsampler.downsample(context, Uri.fromFile(f), 1600, 82)!!)
        assertEquals(800 to 600, w to h)
    }

    @Test fun exifRotationIsApplied() {
        // Camera sensors write landscape pixels + "rotate 90" EXIF for a portrait shot.
        val f = jpeg(2000, 1000, ExifInterface.ORIENTATION_ROTATE_90)
        val (w, h) = dims(ImageDownsampler.downsample(context, Uri.fromFile(f), 1600, 82)!!)
        assertEquals("rotated to portrait, then clamped to 1600", 800 to 1600, w to h)
    }

    @Test fun anUnreadableFileReturnsNullInsteadOfThrowing() {
        val bad = File.createTempFile("bad", ".jpg", context.cacheDir).apply { writeText("not an image") }
        assertEquals(null, ImageDownsampler.downsample(context, Uri.fromFile(bad), 1600, 82))
        assertEquals(null, ImageDownsampler.downsample(context, Uri.fromFile(File(context.cacheDir, "missing.jpg")), 1600, 82))
    }
}
