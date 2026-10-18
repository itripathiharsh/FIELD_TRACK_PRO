package com.fieldtrackpro.android.data.remote

import com.fieldtrackpro.android.data.local.InMemorySharedPreferences
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.utils.SessionManager
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeoutOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/**
 * Session-expiry / refresh hardening: unauthenticated endpoints (a wrong login password produces a 401) must never run
 * the "session expired" path, a wrong re-entered password is not an expired session, and
 * 403 PASSWORD_CHANGE_REQUIRED is turned into a persisted flag + one-shot navigation event.
 */
class AuthHardeningTest {

    private lateinit var server: SimpleHttpServer

    @Before
    fun setup() {
        SessionManager.reset()
        server = SimpleHttpServer()
    }

    @After
    fun tearDown() {
        server.close()
        SessionManager.reset()
    }

    private fun baseUrl() = "http://127.0.0.1:${server.port}/"

    private fun response(url: String, code: Int, auth: String? = "Bearer old", body: String? = null): Response {
        val req = Request.Builder().url(url).apply { if (auth != null) header("Authorization", auth) }.build()
        val b = Response.Builder().request(req).protocol(Protocol.HTTP_1_1).code(code).message("x")
        if (body != null) b.body(body.toResponseBody("application/json".toMediaType()))
        return b.build()
    }

    // ------------------------------------------------------------------ unauthenticated endpoints

    @Test
    fun unauthenticatedEndpointPaths_areRecognised() {
        listOf(
            "/api/v1/auth/login", "/api/v1/auth/refresh", "/api/v1/auth/forgot-password",
            "/api/v1/auth/verify-otp", "/api/v1/auth/reset-password", "/api/v1/auth/logout", "/api/v1/auth/login/"
        ).forEach { assertTrue(it, TokenAuthenticator.isUnauthenticatedEndpoint(it)) }
        listOf("/api/v1/visits", "/api/v1/auth/me", "/api/v1/users/me/password", "/api/v1/payments")
            .forEach { assertFalse(it, TokenAuthenticator.isUnauthenticatedEndpoint(it)) }
    }

    @Test
    fun loginWrongPassword401_doesNotRefreshOrExpireTheSession() = runBlocking {
        val tm = FakeTokenManager(accessToken = "still_good", refreshToken = "refresh_ok")
        val auth = TokenAuthenticator(tm) { baseUrl() }

        // even if a stale bearer was attached, a 401 from /auth/login is the caller's answer
        val retry = auth.authenticate(null, response("${baseUrl()}api/v1/auth/login", 401))

        assertNull(retry)
        assertEquals("no refresh call must be made", 0, server.requestCount.get())
        assertEquals("still_good", tm.getAccessToken())
        assertEquals("refresh_ok", tm.getRefreshToken())
        assertNull("no session-expired event", withTimeoutOrNull(200) { SessionManager.sessionExpiredEvent.first() })
    }

    @Test
    fun requestWithoutAuthorizationHeader_isNotRefreshed() {
        val tm = FakeTokenManager(accessToken = "a", refreshToken = "r")
        val auth = TokenAuthenticator(tm) { baseUrl() }
        assertNull(auth.authenticate(null, response("${baseUrl()}api/v1/visits", 401, auth = null)))
        assertEquals(0, server.requestCount.get())
    }

    @Test
    fun wrongPasswordOnAccountDeletion401_isNotTreatedAsExpiredSession() = runBlocking {
        val tm = FakeTokenManager(accessToken = "a", refreshToken = "r")
        val auth = TokenAuthenticator(tm) { baseUrl() }
        val body = """{"error":{"code":"AUTH_INVALID_PASSWORD","message":"Incorrect password."}}"""

        val retry = auth.authenticate(null, response("${baseUrl()}api/v1/auth/me", 401, body = body))

        assertNull(retry)
        assertEquals("no refresh burned for a wrong password", 0, server.requestCount.get())
        assertEquals("a", tm.getAccessToken())
        assertNull(withTimeoutOrNull(200) { SessionManager.sessionExpiredEvent.first() })
    }

    @Test
    fun expiredAccessToken_stillRefreshesNormally() {
        server.enqueueResponse(200, """{"access_token":"n","refresh_token":"nr","token_type":"bearer"}""")
        val tm = FakeTokenManager(accessToken = "old", refreshToken = "r")
        val retry = TokenAuthenticator(tm) { baseUrl() }
            .authenticate(null, response("${baseUrl()}api/v1/visits", 401, auth = "Bearer old"))
        assertEquals("Bearer n", retry?.header("Authorization"))
    }

    // ------------------------------------------------------------------ PASSWORD_CHANGE_REQUIRED

    @Test
    fun passwordChangeRequired_pureDetection() {
        val body = """{"error":{"code":"PASSWORD_CHANGE_REQUIRED","message":"Change your password"}}"""
        assertTrue(PasswordChangeRequiredInterceptor.isPasswordChangeRequired(403, body))
        assertFalse(PasswordChangeRequiredInterceptor.isPasswordChangeRequired(401, body))
        assertFalse(PasswordChangeRequiredInterceptor.isPasswordChangeRequired(403, """{"error":{"code":"FORBIDDEN","message":"no"}}"""))
        assertFalse(PasswordChangeRequiredInterceptor.isPasswordChangeRequired(403, null))
        assertFalse(PasswordChangeRequiredInterceptor.isPasswordChangeRequired(403, "not json"))
    }

    @Test
    fun interceptor_setsPersistedFlag_andEmitsOneShotNavigationEvent_withoutChangingTheResponse() = runBlocking {
        server.enqueueResponse(403, """{"error":{"code":"PASSWORD_CHANGE_REQUIRED","message":"Change your password"}}""")
        val tm = TokenManager(null, InMemorySharedPreferences())
        assertFalse(tm.isPasswordChangeRequired())
        val client = OkHttpClient.Builder().addInterceptor(PasswordChangeRequiredInterceptor(tm)).build()

        client.newCall(Request.Builder().url("${baseUrl()}api/v1/visits").build()).execute().use { resp ->
            assertEquals(403, resp.code)
            assertTrue("caller still sees the body", resp.body!!.string().contains("PASSWORD_CHANGE_REQUIRED"))
        }

        assertTrue(tm.isPasswordChangeRequired())
        assertNotNull(withTimeoutOrNull(1000) { SessionManager.passwordChangeRequiredEvent.first() })
        assertNull("one-shot", withTimeoutOrNull(200) { SessionManager.passwordChangeRequiredEvent.first() })
    }

    @Test
    fun interceptor_ignoresOrdinary403() = runBlocking {
        server.enqueueResponse(403, """{"error":{"code":"FORBIDDEN","message":"nope"}}""")
        val tm = TokenManager(null, InMemorySharedPreferences())
        val client = OkHttpClient.Builder().addInterceptor(PasswordChangeRequiredInterceptor(tm)).build()
        client.newCall(Request.Builder().url("${baseUrl()}api/v1/visits").build()).execute().close()
        assertFalse(tm.isPasswordChangeRequired())
        assertNull(withTimeoutOrNull(200) { SessionManager.passwordChangeRequiredEvent.first() })
    }

    @Test
    fun tokenManager_flagRoundTripAndClearedOnLogout() {
        val tm = TokenManager(null, InMemorySharedPreferences())
        tm.saveTokens("a", "r")
        tm.setPasswordChangeRequired(true)
        assertTrue(tm.isPasswordChangeRequired())
        tm.setPasswordChangeRequired(false)
        assertFalse(tm.isPasswordChangeRequired())
        tm.setPasswordChangeRequired(true)
        tm.clear()
        assertFalse("flag must not survive logout", tm.isPasswordChangeRequired())
    }
}
