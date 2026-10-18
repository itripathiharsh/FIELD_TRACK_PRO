package com.fieldtrackpro.android.data.remote

import android.util.Log
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.LoginResponse
import com.fieldtrackpro.android.data.model.RefreshRequest
import com.google.gson.Gson
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

/**
 * The ONE place that performs a refresh-token exchange. Every refresh in the app goes through [refresh]'s lock
 * (TokenAuthenticator on a 401, on OkHttp threads), so N concurrent 401s - UI calls, WorkManager uploads - produce
 * exactly ONE refresh call and never present the same single-use refresh token twice (the backend treats reuse
 * beyond a 10 s grace as theft and revokes the whole token family).
 *
 * SplashScreen no longer refreshes at cold start at all (it routes from stored state, see StartRouting), so there
 * is no longer a caller outside this lock.
 *
 * Only a 401/403 from the refresh endpoint ends the session ([RefreshOutcome.Rejected] clears it); network errors
 * and 5xx are [RefreshOutcome.Transient] and never log the user out.
 */
object TokenRefreshCoordinator {
    private const val TAG = "TokenRefreshCoordinator"
    private val lock = Any()
    private val gson = Gson()
    private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()

    private val refreshHttpClient: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(15, TimeUnit.SECONDS)
            .build()
    }

    sealed class RefreshOutcome {
        class Success(val tokens: LoginResponse) : RefreshOutcome()
        object Rejected : RefreshOutcome()
        object Transient : RefreshOutcome()
        /** No refresh token to try - never attempted a network call. */
        object NoToken : RefreshOutcome()
    }

    /**
     * Synchronized end-to-end refresh: reads the current refresh token, calls
     * the backend, and on success/rejection updates `tokenManager` itself
     * (saves the new pair, or clears the session) so every caller sees
     * consistent state. On Transient, the session is left untouched.
     */
    fun refresh(tokenManager: TokenManager, baseUrl: String): RefreshOutcome {
        synchronized(lock) {
            val refreshToken = tokenManager.getRefreshToken()
            if (refreshToken.isNullOrBlank()) {
                return RefreshOutcome.NoToken
            }
            val outcome = performRefresh(refreshToken, baseUrl)
            when (outcome) {
                is RefreshOutcome.Success -> tokenManager.saveTokens(outcome.tokens.accessToken, outcome.tokens.refreshToken)
                RefreshOutcome.Rejected -> tokenManager.clear()
                RefreshOutcome.Transient, RefreshOutcome.NoToken -> { /* session untouched */ }
            }
            return outcome
        }
    }

    private fun performRefresh(refreshToken: String, baseUrl: String): RefreshOutcome {
        return try {
            val url = if (baseUrl.endsWith("/")) "${baseUrl}api/v1/auth/refresh" else "$baseUrl/api/v1/auth/refresh"
            val requestBody = gson.toJson(RefreshRequest(refreshToken)).toRequestBody(JSON_MEDIA_TYPE)
            val request = Request.Builder().url(url).post(requestBody).build()

            refreshHttpClient.newCall(request).execute().use { response ->
                when {
                    response.isSuccessful -> {
                        val bodyString = response.body?.string()
                        val parsed = if (!bodyString.isNullOrBlank()) {
                            gson.fromJson(bodyString, LoginResponse::class.java)
                        } else null
                        if (parsed != null && !parsed.accessToken.isNullOrBlank() && !parsed.refreshToken.isNullOrBlank()) {
                            RefreshOutcome.Success(parsed)
                        } else {
                            RefreshOutcome.Transient
                        }
                    }
                    response.code == 401 || response.code == 403 -> {
                        Log.w(TAG, "Refresh endpoint rejected token: HTTP ${response.code}")
                        RefreshOutcome.Rejected
                    }
                    else -> {
                        Log.w(TAG, "Refresh endpoint returned HTTP ${response.code}")
                        RefreshOutcome.Transient
                    }
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "Network error during token refresh: ${e.message}")
            RefreshOutcome.Transient
        }
    }
}
