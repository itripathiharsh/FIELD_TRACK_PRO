package com.fieldtrackpro.android.premiumui

import androidx.lifecycle.Lifecycle
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.remote.TransientRetryInterceptor
import com.fieldtrackpro.android.ui.navigation.BackNavigationGuard
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.io.IOException
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException

class BackNavigationGuardTest {
    @Test fun popsOnlyFromAResumedDestinationWithSomethingBelow() {
        assertTrue(BackNavigationGuard.canPop(Lifecycle.State.RESUMED, hasPreviousDestination = true))
    }

    @Test fun secondTapDuringTransitionIsIgnored() {
        // After the first pop the destination underneath is only STARTED until its transition finishes.
        assertFalse(BackNavigationGuard.canPop(Lifecycle.State.STARTED, hasPreviousDestination = true))
        assertFalse(BackNavigationGuard.canPop(Lifecycle.State.CREATED, hasPreviousDestination = true))
        assertFalse(BackNavigationGuard.canPop(null, hasPreviousDestination = true))
    }

    @Test fun neverPopsTheLastDestination() {
        assertFalse(BackNavigationGuard.canPop(Lifecycle.State.RESUMED, hasPreviousDestination = false))
    }
}

class RetryPolicyTest {
    @Test fun timeoutsAndNoNetworkAreNotRetried() {
        assertFalse(TransientRetryInterceptor.isRetryableIOException(SocketTimeoutException("read timed out")))
        assertFalse(TransientRetryInterceptor.isRetryableIOException(UnknownHostException("no dns")))
    }

    @Test fun connectionFailuresAreRetried() {
        assertTrue(TransientRetryInterceptor.isRetryableIOException(ConnectException("refused")))
        assertTrue(TransientRetryInterceptor.isRetryableIOException(IOException("unexpected end of stream")))
    }

    @Test fun timeoutsAreBounded() {
        assertEquals(10L, ApiClient.CONNECT_TIMEOUT_SECONDS)
        assertEquals(20L, ApiClient.DEFAULT_TIMEOUT_SECONDS)
    }
}

/**
 * The release backend URL is decided in app/build.gradle.kts (Gradle logic cannot run in a unit test), so this guards
 * the build script itself: production is the default, the Render host is never the release value, and the release
 * guard refuses it.
 */
class ReleaseConfigGuardTest {
    private val script: String = listOf(File("build.gradle.kts"), File("app/build.gradle.kts"))
        .first { it.exists() && it.readText().contains("android {") }
        .readText()

    @Test fun productionIsTheDefaultReleaseUrl() {
        assertTrue(script.contains("val productionBaseUrl = \"https://51-79-158-138.sslip.io/\""))
        assertTrue(script.contains("buildConfigField(\"String\", \"BASE_URL\", buildConfigString(releaseBaseUrlValue))"))
    }

    @Test fun updateManifestUrlIsHttpsOnAnAllowedHost() {
        assertTrue(script.contains("val defaultUpdateManifestUrl = \"https://fieldtrack-pro-rosy.vercel.app/downloads/app-update.json\""))
        assertTrue(script.contains("UPDATE_MANIFEST_URL must be an https:// URL on one of UPDATE_ALLOWED_HOSTS"))
    }

    @Test fun renderHostIsBlockedAndNeverTheReleaseValue() {
        assertFalse(script.contains("\"https://fieldtrackpro-backend-s7hs.onrender.com/\""))
        assertTrue(script.contains("\"onrender.com\""))
        assertTrue(script.contains("RELEASE_BASE_URL points at a blocked host"))
        assertTrue(script.contains("RELEASE_BASE_URL must be an https:// URL"))
    }
}
