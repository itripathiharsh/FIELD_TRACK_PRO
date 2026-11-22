package com.fieldtrackpro.android.screens

import android.graphics.Bitmap
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Density
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.unit.dp
import com.fieldtrackpro.android.BuildConfig
import com.fieldtrackpro.android.ui.components.PrimaryButton
import com.fieldtrackpro.android.ui.screens.auth.LoginLayout
import com.fieldtrackpro.android.ui.screens.dashboard.BeatItem
import com.fieldtrackpro.android.ui.screens.dashboard.BeatUi
import com.fieldtrackpro.android.ui.screens.dashboard.DashboardContent
import com.fieldtrackpro.android.ui.screens.dashboard.DashboardUi
import com.fieldtrackpro.android.ui.screens.dashboard.WorkdayStatus
import com.fieldtrackpro.android.ui.screens.profile.ProfileContent
import com.fieldtrackpro.android.ui.screens.profile.ProfileUi
import com.fieldtrackpro.android.ui.screens.splash.SplashContent
import com.fieldtrackpro.android.ui.theme.FieldTrackProTheme
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.File
import java.io.FileOutputStream

/**
 * Design-review screenshots of the redesigned screens, rendered on the JVM with DEMO data (no backend, no accounts).
 * Skipped in the normal suite; run with:  ./gradlew testDebugUnitTest -PcaptureScreens=true --tests "*ScreenshotCaptureTest*"
 * Output: <repo>/design-review/screens/
 */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
abstract class ScreenshotCaptureBase(private val sizeLabel: String) {
    @get:Rule val rule = createAndroidComposeRule<androidx.activity.ComponentActivity>()

    @Before fun gate() = assumeTrue(System.getProperty("captureScreens") == "true")

    protected fun shoot(name: String, fontScale: Float = 1f, content: @Composable () -> Unit) {
        rule.setContent {
            val base = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(base.density, base.fontScale * fontScale)) {
                FieldTrackProTheme { content() }
            }
        }
        rule.waitForIdle()
        // PixelCopy (captureToImage) is not available under Robolectric: draw the content view directly.
        val view = rule.activity.findViewById<android.view.View>(android.R.id.content)
        val bmp = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
        view.draw(android.graphics.Canvas(bmp))
        val dir = File(System.getProperty("screensDir") ?: "build/screens").apply { mkdirs() }
        val scaleTag = if (fontScale != 1f) "_font$fontScale" else ""
        FileOutputStream(File(dir, "${name}_$sizeLabel$scaleTag.png")).use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    private val demo = DashboardUi(
        greeting = "Good morning",
        userName = "Aarav (demo)",
        dateLabel = "Sun, 22 Nov",
        workdayStatus = WorkdayStatus.STARTED,
        workdayDetail = "Clocked in at 9:12 AM",
        isWorkdayLoading = false,
        isCapturingLocation = false,
        isSubmitting = false,
        workdayError = null,
        visitsDone = 3,
        visitsTotal = 8,
        adhocVisits = 1,
        collectedToday = 125450.50,
        notVerified = 45450.50,
        verified = 80000.0,
        beat = BeatUi.Loaded(
            planned = listOf(
                BeatItem("1", "Demo Kirana Store", "10:00 AM", "COMPLETED"),
                BeatItem("2", "Sample Traders", "11:30 AM", "CHECKED_IN"),
                BeatItem("3", "Example Agencies", "1:00 PM", "PENDING"),
                BeatItem("4", "Test Mart", "3:30 PM", "PENDING")
            ),
            plannedTotal = 7
        ),
        pendingOffline = 0
    )

    @Composable
    private fun dashboard(ui: DashboardUi) {
        DashboardContent(ui, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {})
    }

    @Test fun splash() = shoot("01_splash") { SplashContent(animate = false) }

    @Test fun login() = shoot("02_login") {
        LoginLayout(title = "Sign in", subtitle = "Use your registered mobile number or email.") {
            OutlinedTextField(value = "", onValueChange = {}, label = { Text("Mobile number or email") }, modifier = Modifier.fillMaxWidth())
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(value = "", onValueChange = {}, label = { Text("Password") }, modifier = Modifier.fillMaxWidth())
            Spacer(Modifier.height(16.dp))
            PrimaryButton("Sign in", onClick = {}, enabled = false, modifier = Modifier.fillMaxWidth())
        }
    }

    @Test fun dashboardOnDuty() = shoot("03_dashboard_on_duty") { dashboard(demo) }

    @Test fun dashboardOnDutyLargeFont() = shoot("03_dashboard_on_duty", fontScale = 1.3f) { dashboard(demo) }

    @Test fun dashboardNotStarted() = shoot("04_dashboard_not_started") {
        dashboard(
            demo.copy(
                workdayStatus = WorkdayStatus.NOT_STARTED, workdayDetail = "Start your day with GPS to begin visits",
                visitsDone = 0, visitsTotal = 0, adhocVisits = 0, collectedToday = 0.0, notVerified = 0.0, verified = 0.0,
                beat = BeatUi.Loaded(emptyList(), 0)
            )
        )
    }

    @Test fun dashboardErrorStates() = shoot("05_dashboard_errors") {
        dashboard(
            demo.copy(
                workdayStatus = WorkdayStatus.UNKNOWN, workdayDetail = null,
                workdayError = "GPS signal is too weak (±480 m). Move near a window or outdoors and try again.",
                beat = BeatUi.Error("Can't reach the server. Check your connection."),
                pendingOffline = 2
            )
        )
    }

    private val release = com.fieldtrackpro.android.update.UpdateManifest(
        schema = 1, packageName = "com.fieldtrackpro.android", versionCode = 7, versionName = "1.3.1",
        apkUrl = "https://fieldtrack-pro-rosy.vercel.app/downloads/releases/FieldTrackPro-1.3.1-7.apk",
        apkSha256 = "0".repeat(64), apkSizeBytes = 24_380_000, minSupportedVersionCode = 6, mandatory = false,
        releaseNotes = listOf("Start Day now asks for location permission", "Faster dashboard loading", "Payment amounts keep paise")
    )

    @Composable
    private fun dialogFrame(state: com.fieldtrackpro.android.update.UpdateUiState) {
        // The real popup is a Dialog window; render the same card over a scrim so it can be captured.
        androidx.compose.foundation.layout.Box(
            Modifier.fillMaxSize().background(androidx.compose.ui.graphics.Color(0xFF0B1426).copy(alpha = 0.55f)),
            contentAlignment = androidx.compose.ui.Alignment.Center
        ) {
            androidx.compose.material3.Surface(
                shape = androidx.compose.foundation.shape.RoundedCornerShape(24.dp),
                color = androidx.compose.ui.graphics.Color.White,
                modifier = Modifier.padding(horizontal = 20.dp).fillMaxWidth()
            ) {
                com.fieldtrackpro.android.ui.screens.update.UpdateCardContent(state, mandatory = false, {}, {}, {})
            }
        }
    }

    @Test fun updateOptional() = shoot("07_update_optional") {
        dialogFrame(com.fieldtrackpro.android.update.UpdateUiState.Available(release, false, null))
    }

    @Test fun updateDownloading() = shoot("08_update_downloading") {
        dialogFrame(com.fieldtrackpro.android.update.UpdateUiState.Downloading(release, false, 9_750_000, 24_380_000))
    }

    @Test fun updateFailed() = shoot("09_update_failed") {
        dialogFrame(
            com.fieldtrackpro.android.update.UpdateUiState.Failed(
                release, false, "Download interrupted. Check your internet connection and tap Retry; it continues where it stopped."
            )
        )
    }

    @Test fun updatePermission() = shoot("10_update_install_permission") {
        dialogFrame(com.fieldtrackpro.android.update.UpdateUiState.NeedsInstallPermission(release, false))
    }

    @Test fun updateMandatory() = shoot("11_update_mandatory") {
        com.fieldtrackpro.android.ui.screens.update.MandatoryUpdateScreen(
            state = com.fieldtrackpro.android.update.UpdateUiState.Available(
                release.copy(mandatory = true), true, "This version of FieldTrack Pro is no longer supported."
            ),
            onUpdateNow = {}, onOpenInstallPermission = {}, onExitApp = {}
        )
    }

    @Test fun profile() = shoot("06_profile") {
        ProfileContent(
            profile = ProfileUi(
                name = "Aarav (demo)", role = "Employee", phone = "98XXXXXX10", email = null,
                employeeCode = "DEMO-01", territory = "Kanpur", appVersion = BuildConfig.VERSION_NAME
            ),
            pendingCount = 0, onBack = {}, onSyncQueue = {}, onPrivacy = {}, onLogout = {}, onRequestDeletion = {}
        )
    }
}

@Config(sdk = [34], qualifiers = "w360dp-h640dp-xhdpi", application = android.app.Application::class)
class ScreenshotSmallPhone : ScreenshotCaptureBase("360x640")

@Config(sdk = [34], qualifiers = "w393dp-h852dp-xxhdpi", application = android.app.Application::class)
class ScreenshotMediumPhone : ScreenshotCaptureBase("393x852")

@Config(sdk = [34], qualifiers = "w412dp-h915dp-xxhdpi", application = android.app.Application::class)
class ScreenshotLargePhone : ScreenshotCaptureBase("412x915")
