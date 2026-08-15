package com.fieldtrackpro.android.utils

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * P1-10: ImageDownsampler.calculateInSampleSize has no Android framework
 * dependency (no Bitmap/BitmapFactory/Context), so it's covered directly by
 * a plain JVM unit test. The bitmap decode/compress/EXIF-rotation pipeline
 * itself (downsample(), decodeSampledBitmapForDisplay()) depends on
 * android.graphics classes unavailable outside an emulator/instrumented
 * test - this project has neither configured (Robolectric or
 * androidTest), so that part is verified by compilation + manual/device
 * review only. See the P1 report.
 */
class ImageDownsamplerTest {

    @Test
    fun imageSmallerThanTarget_needsNoDownsampling() {
        assertEquals(1, ImageDownsampler.calculateInSampleSize(800, 600, ImageDownsampler.MAX_DIMENSION_PX))
    }

    @Test
    fun imageExactlyAtTarget_needsNoDownsampling() {
        assertEquals(1, ImageDownsampler.calculateInSampleSize(1600, 1600, ImageDownsampler.MAX_DIMENSION_PX))
    }

    @Test
    fun typical12MpPhoto_isDownsampled() {
        // A 4000x3000 (12MP) photo, this app's realistic camera output.
        val sampleSize = ImageDownsampler.calculateInSampleSize(4000, 3000, ImageDownsampler.MAX_DIMENSION_PX)
        assertTrue("expected downsampling for a 12MP photo, got sampleSize=$sampleSize", sampleSize > 1)
        // The result must still land close to (at or above) the target after
        // dividing by the chosen power-of-two sample size.
        assertTrue(4000 / sampleSize >= ImageDownsampler.MAX_DIMENSION_PX / 2)
    }

    @Test
    fun sampleSizeIsAlwaysAPowerOfTwo() {
        val sampleSize = ImageDownsampler.calculateInSampleSize(4000, 3000, ImageDownsampler.MAX_DIMENSION_PX)
        assertTrue("sampleSize ($sampleSize) must be a power of two", (sampleSize and (sampleSize - 1)) == 0)
    }

    @Test
    fun veryLargePanorama_downsamplesProportionallyOnBothDimensions() {
        val sampleSize = ImageDownsampler.calculateInSampleSize(8000, 2000, ImageDownsampler.MAX_DIMENSION_PX)
        // The long edge (8000) must end up reasonably close to the target.
        assertTrue(8000 / sampleSize <= ImageDownsampler.MAX_DIMENSION_PX * 2)
    }
}
