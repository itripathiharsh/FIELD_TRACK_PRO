package com.fieldtrackpro.android.data.remote

import android.util.Log
import com.fieldtrackpro.android.BuildConfig
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.utils.SessionManager
import okhttp3.Authenticator
import okhttp3.Request
import okhttp3.Response
import okhttp3.Route
import java.io.IOException

/**
 * Global OkHttp Authenticator for automatic 401 Bearer token refresh.
 *
 * APP-AUTH-001:
 * - Single coordinated refresh: the actual network call is delegated to
 *   TokenRefreshCoordinator, whose lock is shared with every OTHER caller
 *   that can trigger a refresh (e.g. SplashScreen on cold start) - not just
 *   concurrent requests inside this Authenticator.
 * - Single retry limit: prevents infinite retry loops.
 * - Clean session teardown: clears credentials and emits session expiration event if refresh fails.
 */
class TokenAuthenticator(
    private val tokenManager: TokenManager,
    private val baseUrlProvider: () -> String = { BuildConfig.BASE_URL }
) : Authenticator {

    companion object {
        private const val TAG = "TokenAuthenticator"
        // Serialises concurrent 401s within THIS process's Authenticator so N requests
        // failing on the same stale token produce exactly one refresh call, not N. This is
        // IN ADDITION to (and taken before) TokenRefreshCoordinator's own lock, which is
        // what actually serialises against a non-Authenticator caller like SplashScreen.
        // Always acquired in this order (never the reverse), so nesting the two is deadlock-free.
        private val lock = Any()

        // Endpoints that are reachable WITHOUT a session. A 401 from them means "wrong credentials /
        // bad code", NOT "your session expired": running the refresh/"session expired" path for them
        // would (a) burn a refresh token while the user is merely mistyping a password and (b) log an
        // already-signed-in session out. They are also sent without an Authorization header
        // (see ApiClient's auth interceptor).
        private val UNAUTHENTICATED_PATH_SUFFIXES = listOf(
            "/auth/login",
            "/auth/refresh",
            "/auth/logout",
            "/auth/forgot-password",
            "/auth/verify-otp",
            "/auth/reset-password"
        )

        /** Error codes meaning "the PASSWORD you re-entered is wrong" (e.g. DELETE /auth/me), not "session expired". */
        val PASSWORD_FAILURE_CODES = setOf("AUTH_INVALID_PASSWORD", "INVALID_PASSWORD", "REAUTH_REQUIRED")

        fun isPasswordFailureBody(errorBody: String?): Boolean =
            !errorBody.isNullOrBlank() && ApiErrorParser.parse(401, errorBody).code in PASSWORD_FAILURE_CODES

        fun isUnauthenticatedEndpoint(encodedPath: String): Boolean {
            val path = encodedPath.trimEnd('/')
            return UNAUTHENTICATED_PATH_SUFFIXES.any { path.endsWith(it) }
        }
    }

    override fun authenticate(route: Route?, response: Response): Request? {
        // Prevent infinite loops: only retry once
        if (responseCount(response) >= 2) {
            Log.w(TAG, "Already retried request; aborting to prevent loop")
            return null
        }

        // Wrong password at login, bad OTP, etc.: a 401 here is the caller's answer, not an expiry.
        if (isUnauthenticatedEndpoint(response.request.url.encodedPath)) {
            return null
        }
        // A 401 that says "wrong password" (re-authentication for a destructive action) is not an expired
        // session: do not burn a refresh token on it, hand the answer to the caller to show inline.
        val peeked = try { response.peekBody(8 * 1024L).string() } catch (e: Exception) { null }
        if (isPasswordFailureBody(peeked)) return null
        // Nothing to refresh on behalf of: the request never carried a session.
        if (response.request.header("Authorization").isNullOrBlank()) {
            return null
        }

        synchronized(lock) {
            val currentAccessToken = tokenManager.getAccessToken()
            val requestHeader = response.request.header("Authorization")
            val requestToken = requestHeader?.removePrefix("Bearer ")?.trim()

            // If another thread already refreshed the token and saved a newer one, retry immediately.
            if (currentAccessToken != null && currentAccessToken != requestToken) {
                Log.d(TAG, "Reusing fresh access token obtained by another thread")
                return response.request.newBuilder()
                    .header("Authorization", "Bearer $currentAccessToken")
                    .build()
            }

            Log.i(TAG, "Attempting coordinated token refresh...")
            return when (val outcome = TokenRefreshCoordinator.refresh(tokenManager, baseUrlProvider())) {
                is TokenRefreshCoordinator.RefreshOutcome.Success -> {
                    Log.i(TAG, "Token refresh succeeded; retrying original request")
                    response.request.newBuilder()
                        .header("Authorization", "Bearer ${outcome.tokens.accessToken}")
                        .build()
                }
                TokenRefreshCoordinator.RefreshOutcome.Rejected -> {
                    // The coordinator already cleared the session: 401/403 from the refresh endpoint is
                    // the ONLY thing that logs a user out (never network errors or 5xx).
                    Log.w(TAG, "Token refresh rejected; session ended")
                    SessionManager.notifySessionExpired()
                    null
                }
                TokenRefreshCoordinator.RefreshOutcome.NoToken -> {
                    Log.w(TAG, "No refresh token available; terminating session")
                    tokenManager.clear()
                    SessionManager.notifySessionExpired()
                    null
                }
                TokenRefreshCoordinator.RefreshOutcome.Transient -> {
                    // Network error / server error: keep the session so the user is not logged out
                    // just because connectivity dropped. Returning null here would hand the ORIGINAL
                    // 401 back to the caller unchanged, and SyncErrorPolicy.classify(401) reads that
                    // as AUTH_EXPIRED - pausing sync as if the session had genuinely expired. Throwing
                    // instead fails the call with no HTTP code at all, which classify(null) correctly
                    // reads as RETRYABLE (network failure), so the offline queue just retries later.
                    Log.w(TAG, "Token refresh failed transiently; keeping session")
                    throw IOException("Token refresh failed transiently (network or server error); will retry later")
                }
            }
        }
    }

    private fun responseCount(response: Response): Int {
        var count = 1
        var prior = response.priorResponse
        while (prior != null) {
            count++
            prior = prior.priorResponse
        }
        return count
    }
}
