package com.fieldtrackpro.android.update

import com.fieldtrackpro.android.data.local.InMemorySharedPreferences
import com.google.gson.Gson
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.io.IOException

@OptIn(ExperimentalCoroutinesApi::class)
class AppUpdateControllerTest {
    private val store = UpdateStore(InMemorySharedPreferences())
    private var nowMs = 10_000_000L
    private var served: () -> String = { Gson().toJson(manifest()) }
    private var download: suspend (UpdateManifest, (Long, Long?) -> Unit) -> File = { _, p -> p(500, 1000); p(1000, 1000); apk }
    private var verify: (File, UpdateManifest) -> ApkVerifier.Result = { _, _ -> ApkVerifier.Result.Ok }
    private var canInstall = true
    private val installs = mutableListOf<File>()
    private val apk: File = File.createTempFile("ftupdate", ".apk").apply { deleteOnExit() }

    private fun TestScope.controller(installed: Long = 6, url: String = "https://fieldtrack-pro-rosy.vercel.app/downloads/app-update.json") =
        AppUpdateController(
            scope = this,
            installedVersionCode = { installed },
            expectedPackage = PKG,
            manifestUrl = url,
            allowedHosts = HOSTS,
            store = store,
            now = { nowMs },
            fetchManifest = { served() },
            downloadApk = { m, p -> download(m, p) },
            verifyApk = { f, m -> verify(f, m) },
            canInstall = { canInstall },
            install = { installs += it }
        )

    @Test fun optionalUpdateIsOfferedAndLaterHidesItForADay() = runTest {
        val c = controller()
        c.onAppStart(); advanceUntilIdle()
        assertEquals(UpdateUiState.Available(manifest(), false, null), c.state.value)

        c.later()
        assertEquals(UpdateUiState.Hidden, c.state.value)
        // Re-opening the app the same day: no popup.
        val again = controller()
        again.onAppStart(); advanceUntilIdle()
        assertEquals(UpdateUiState.Hidden, again.state.value)
        // Next day: shown again.
        nowMs += UpdatePolicy.SNOOZE_MS
        val nextDay = controller()
        nextDay.onAppStart(); advanceUntilIdle()
        assertTrue(nextDay.state.value is UpdateUiState.Available)
    }

    @Test fun mandatoryCannotBeDismissedAndSurvivesARestartOffline() = runTest {
        served = { Gson().toJson(manifest(mandatory = true)) }
        val c = controller()
        c.onAppStart(); advanceUntilIdle()
        assertTrue(c.state.value.isMandatory)
        c.later()
        assertTrue(c.state.value.isMandatory)

        // Restart without network: the cached manifest still blocks the app.
        served = { throw IOException("offline") }
        val offline = controller()
        offline.onAppStart()
        assertTrue(offline.state.value.isMandatory)
        advanceUntilIdle()
        assertTrue(offline.state.value.isMandatory)
    }

    @Test fun tamperedOrInvalidManifestChangesNothing() = runTest {
        served = { Gson().toJson(manifest(url = "https://evil.example.com/x.apk")) }
        val c = controller()
        c.onAppStart(); advanceUntilIdle()
        assertEquals(UpdateUiState.Hidden, c.state.value)
        assertEquals(null, store.lastManifestJson())
    }

    @Test fun alreadyOnTheLatestVersionShowsNothing() = runTest {
        val c = controller(installed = 7)
        c.onAppStart(); advanceUntilIdle()
        assertEquals(UpdateUiState.Hidden, c.state.value)
    }

    @Test fun updateNowDownloadsVerifiesAndHandsOffToAndroid() = runTest {
        val c = controller()
        c.onAppStart(); advanceUntilIdle()
        c.updateNow(); advanceUntilIdle()
        assertEquals(listOf(apk), installs)
        assertTrue(c.state.value is UpdateUiState.Installing)

        c.onInstallEvent(InstallEvent.CancelledByUser)
        assertTrue(c.state.value is UpdateUiState.Available) // can try again
    }

    @Test fun signatureRejectionNeverReachesTheInstaller() = runTest {
        verify = { _, _ -> ApkVerifier.Result.Rejected("This update is not signed with the FieldTrack Pro release key, so it was not installed.") }
        val c = controller()
        c.onAppStart(); advanceUntilIdle()
        c.updateNow(); advanceUntilIdle()
        assertTrue(installs.isEmpty())
        val failed = c.state.value as UpdateUiState.Failed
        assertTrue(failed.message.contains("release key"))
        assertFalse(apk.exists())
    }

    @Test fun interruptedDownloadCanBeRetried() = runTest {
        var attempts = 0
        download = { _, p -> attempts++; if (attempts == 1) { p(300, 1000); throw IOException("connection reset") } else apk }
        val c = controller()
        c.onAppStart(); advanceUntilIdle()
        c.updateNow(); advanceUntilIdle()
        assertTrue((c.state.value as UpdateUiState.Failed).message.contains("Retry"))
        c.updateNow(); advanceUntilIdle()
        assertEquals(2, attempts)
        assertEquals(listOf(apk), installs)
    }

    @Test fun shaMismatchIsReportedAsVerificationFailure() = runTest {
        download = { _, _ -> throw UpdateNetwork.VerificationException("Downloaded file failed the SHA-256 check") }
        val c = controller()
        c.onAppStart(); advanceUntilIdle()
        c.updateNow(); advanceUntilIdle()
        assertTrue((c.state.value as UpdateUiState.Failed).message.contains("SHA-256"))
        assertTrue(installs.isEmpty())
    }

    @Test fun installPermissionFlowResumesAfterTheUserAllowsIt() = runTest {
        canInstall = false
        val c = controller()
        c.onAppStart(); advanceUntilIdle()
        c.updateNow(); advanceUntilIdle()
        assertTrue(c.state.value is UpdateUiState.NeedsInstallPermission)
        assertTrue(installs.isEmpty())

        canInstall = true // user switched on "Install unknown apps" and came back
        c.onResume(); advanceUntilIdle()
        assertEquals(listOf(apk), installs)
    }

    @Test fun disabledWhenNoManifestUrlIsConfigured() = runTest {
        val c = controller(url = "")
        c.onAppStart(); advanceUntilIdle()
        assertEquals(UpdateUiState.Hidden, c.state.value)
    }
}
