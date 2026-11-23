package com.fieldtrackpro.android.screens

import android.graphics.Bitmap
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Text
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.getUnclippedBoundsInRoot
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.fieldtrackpro.android.ui.screens.proof.CaptureLayout
import com.fieldtrackpro.android.ui.theme.FieldTrackProTheme
import com.fieldtrackpro.android.utils.AccuracyBand
import com.fieldtrackpro.android.utils.ProofFix
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.File
import java.io.FileOutputStream

/**
 * The capture controls must sit fully above the system navigation area. The bar is simulated by a strip drawn over
 * the bottom [barHeight] of the window (gesture bar ~24 dp, 3-button bar ~48 dp).
 */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(application = android.app.Application::class, qualifiers = "w360dp-h780dp-xxhdpi")
class CaptureLayoutTest {
    @get:Rule val rule = createAndroidComposeRule<androidx.activity.ComponentActivity>()

    private fun render(barHeight: Dp, name: String): Pair<Dp, Dp> {
        rule.setContent {
            FieldTrackProTheme {
                Box(Modifier.fillMaxSize()) {
                    CaptureLayout(
                        preview = { Box(Modifier.fillMaxSize().background(Color(0xFF6B5B4B))) { Text("camera preview", color = Color.White, modifier = Modifier.align(Alignment.Center)) } },
                        insets = WindowInsets(top = 24.dp, bottom = barHeight),
                        onCancel = {}, band = AccuracyBand.NONE, fix = null as ProofFix?, blockedText = "Waiting for GPS...",
                        locationEnabled = true, onTurnOnLocation = {}, errorText = null,
                        shutterReady = false, busy = false, onShutter = {}
                    )
                    // The system navigation bar, drawn on top exactly where Android would put it.
                    Box(Modifier.align(Alignment.BottomCenter).fillMaxWidth().height(barHeight).background(Color(0xCC444444))) {
                        Box(Modifier.align(Alignment.Center).size(width = 100.dp, height = 4.dp).background(Color.White))
                    }
                }
            }
        }
        rule.waitForIdle()
        if (System.getProperty("captureScreens") == "true") {
            val view = rule.activity.findViewById<android.view.View>(android.R.id.content)
            val bmp = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
            view.draw(android.graphics.Canvas(bmp))
            val dir = File(System.getProperty("screensDir") ?: "build/screens").apply { mkdirs() }
            FileOutputStream(File(dir, "$name.png")).use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
        }
        val shutter = rule.onNodeWithContentDescription("Take photo")
        shutter.assertIsDisplayed()
        val b = shutter.getUnclippedBoundsInRoot()
        val root = rule.onNodeWithText("CANCEL").getUnclippedBoundsInRoot()
        return b.bottom to root.top
    }

    private fun windowHeight(): Dp = 780.dp

    @Test fun shutterClearsGestureBar() {
        val bar = 24.dp
        val (bottom, cancelTop) = render(bar, "capture_layout_gesture_nav")
        assertTrue("shutter bottom $bottom must be above the bar at ${windowHeight() - bar}", bottom <= windowHeight() - bar)
        assertTrue("Cancel must sit below the status bar area (top=$cancelTop)", cancelTop >= 24.dp)
    }

    @Test fun shutterClearsThreeButtonBar() {
        val bar = 48.dp
        val (bottom, _) = render(bar, "capture_layout_three_button_nav")
        assertTrue("shutter bottom $bottom must be above the bar at ${windowHeight() - bar}", bottom <= windowHeight() - bar)
    }

    /** Real system-bar insets delivered through the view hierarchy (what Android does), not a parameter. */
    @Test fun shutterClearsBarWhenInsetsAreDispatchedThroughTheWindow() {
        val barDp = 48
        rule.setContent {
            FieldTrackProTheme {
                androidx.compose.foundation.layout.Box(Modifier.fillMaxSize()) {
                    CaptureLayout(
                        preview = { androidx.compose.foundation.layout.Box(Modifier.fillMaxSize().background(Color.DarkGray)) },
                        onCancel = {}, band = AccuracyBand.NONE, fix = null as ProofFix?, blockedText = null,
                        locationEnabled = true, onTurnOnLocation = {}, errorText = null,
                        shutterReady = true, busy = false, onShutter = {}
                    )
                }
            }
        }
        rule.waitForIdle()
        val density = rule.activity.resources.displayMetrics.density
        val px = (barDp * density).toInt()
        rule.runOnUiThread {
            val root = rule.activity.findViewById<android.view.ViewGroup>(android.R.id.content).getChildAt(0)
            val insets = androidx.core.view.WindowInsetsCompat.Builder()
                .setInsets(androidx.core.view.WindowInsetsCompat.Type.navigationBars(), androidx.core.graphics.Insets.of(0, 0, 0, px))
                .setInsets(androidx.core.view.WindowInsetsCompat.Type.statusBars(), androidx.core.graphics.Insets.of(0, 24, 0, 0))
                .build()
            androidx.core.view.ViewCompat.dispatchApplyWindowInsets(root, insets)
        }
        rule.waitForIdle()
        val bottom = rule.onNodeWithContentDescription("Take photo").getUnclippedBoundsInRoot().bottom
        assertTrue("shutter bottom $bottom must be above ${windowHeight() - barDp.dp}", bottom <= windowHeight() - barDp.dp)
    }
}
