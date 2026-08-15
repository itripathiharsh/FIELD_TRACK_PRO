package com.fieldtrackpro.android

import com.fieldtrackpro.android.data.remote.ApiClient
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test

/**
 * P0-3 regression coverage: a production (release) build must never accept
 * an arbitrary API base-URL override - that would let anyone redirect all
 * API traffic, including the bearer token on every request, to an attacker-
 * controlled endpoint. Run under both testDebugUnitTest and
 * testReleaseUnitTest so both branches of the guard are actually exercised,
 * not just asserted.
 */
class ApiClientProductionSecurityTest {

    @Test
    fun setCustomBaseUrl_onlyTakesEffectInDebugBuilds() {
        val original = ApiClient.getBaseUrl()
        val attempted = "http://attacker.example.com/"

        ApiClient.setCustomBaseUrl(attempted)

        if (BuildConfig.DEBUG) {
            assertEquals(
                "debug/QA builds must still support the developer base-URL override",
                attempted,
                ApiClient.getBaseUrl(),
            )
        } else {
            assertNotEquals(
                "P0-3: a release build must never accept an arbitrary API base URL override",
                attempted,
                ApiClient.getBaseUrl(),
            )
            assertEquals(original, ApiClient.getBaseUrl())
        }
    }
}
