package com.fieldtrackpro.android.data.remote

import android.util.Log
import com.fieldtrackpro.android.BuildConfig
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.LoginResponse
import com.fieldtrackpro.android.data.model.RefreshRequest
import com.fieldtrackpro.android.utils.SessionManager
import com.google.gson.Gson
import okhttp3.Authenticator
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.Route
import java.util.concurrent.TimeUnit

/**
 * Global OkHttp Authenticator for automatic 401 Bearer token refresh.
 *
 * APP-AUTH-001:
 * - Single coordinated refresh: avoids refresh storm when multiple concurrent calls 401.
 * - Thread-safe synchronization: first thread performs refresh, subsequent threads reuse the new token.
 * - Single retry limit: prevents infinite retry loops.
 * - Clean session teardown: clears credentials and emits session expiration event if refresh fails.
 */
class TokenAuthenticator(
    private val tokenManager: TokenManager,
    private val baseUrlProvider: () -> String = { BuildConfig.BASE_URL }
) : Authenticator {

    companion object {
        private const val TAG = "TokenAuthenticator"
        private val lock = Any()
        private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()
        private val gson = Gson()

        // Dedicated lightweight unauthenticated client for refresh calls
        private val refreshHttpClient: OkHttpClient by lazy {
            OkHttpClient.Builder()
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(15, TimeUnit.SECONDS)
                .build()
        }
    }

    override fun authenticate(route: Route?, response: Response): Request? {
        // Prevent infinite loops: only retry once
        if (responseCount(response) >= 2) {
            Log.w(TAG, "Already retried request; aborting to prevent loop")
            return null
        }

        synchronized(lock) {
            val currentAccessToken = tokenManager.getAccessToken()
            val requestHeader = response.request.header("Authorization")
            val requestToken = requestHeader?.removePrefix("Bearer ")?.trim()

            // If another thread already refreshed the token and saved a newer one, retry immediately
            if (currentAccessToken != null && currentAccessToken != requestToken) {
                Log.d(TAG, "Reusing fresh access token obtained by another thread")
                return response.request.newBuilder()
                    .header("Authorization", "Bearer $currentAccessToken")
                    .build()
            }

            val refreshToken = tokenManager.getRefreshToken()
            if (refreshToken.isNullOrBlank()) {
                Log.w(TAG, "No refresh token available; terminating session")
                handleSessionExpired()
                return null
            }

            Log.i(TAG, "Attempting coordinated token refresh...")
            val newTokens = performTokenRefresh(refreshToken)
            return if (newTokens != null) {
                tokenManager.saveTokens(newTokens.accessToken, newTokens.refreshToken)
                Log.i(TAG, "Token refresh succeeded; retrying original request")
                response.request.newBuilder()
                    .header("Authorization", "Bearer ${newTokens.accessToken}")
                    .build()
            } else {
                Log.w(TAG, "Token refresh rejected; clearing credentials")
                handleSessionExpired()
                null
            }
        }
    }

    private fun performTokenRefresh(refreshToken: String): LoginResponse? {
        return try {
            val baseUrl = baseUrlProvider()
            val url = if (baseUrl.endsWith("/")) "${baseUrl}api/v1/auth/refresh" else "$baseUrl/api/v1/auth/refresh"
            val requestBody = gson.toJson(RefreshRequest(refreshToken)).toRequestBody(JSON_MEDIA_TYPE)

            val request = Request.Builder()
                .url(url)
                .post(requestBody)
                .build()

            val response = refreshHttpClient.newCall(request).execute()
            if (response.isSuccessful) {
                val bodyString = response.body?.string()
                if (!bodyString.isNullOrBlank()) {
                    gson.fromJson(bodyString, LoginResponse::class.java)
                } else null
            } else {
                Log.e(TAG, "Refresh endpoint returned HTTP ${response.code}")
                null
            }
        } catch (e: Exception) {
            Log.e(TAG, "Network error during token refresh: ${e.message}")
            null
        }
    }

    private fun handleSessionExpired() {
        tokenManager.clear()
        SessionManager.notifySessionExpired()
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
