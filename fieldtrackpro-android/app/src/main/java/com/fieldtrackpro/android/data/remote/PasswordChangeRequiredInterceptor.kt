package com.fieldtrackpro.android.data.remote

import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.utils.SessionManager
import okhttp3.Interceptor
import okhttp3.Response

/**
 * Backend contract: while an account has `must_change_password = true`, every other authenticated
 * endpoint answers `403 {"error":{"code":"PASSWORD_CHANGE_REQUIRED"}}`.
 *
 * This interceptor recognises that answer on ANY call (UI, workers, uploads), persists the flag in
 * [TokenManager] (so routing / sync pause survive a process kill) and emits a ONE-SHOT navigation event
 * ([SessionManager.passwordChangeRequiredEvent]). The response itself is passed through unchanged
 * (only peeked), so callers still see a 403 - queue processors must map it to "pause", never to a
 * rejection/conflict (see [com.fieldtrackpro.android.data.local.SyncErrorPolicy.isPasswordChangeRequired]).
 */
class PasswordChangeRequiredInterceptor(private val tokenManager: TokenManager) : Interceptor {

    companion object {
        const val ERROR_CODE = "PASSWORD_CHANGE_REQUIRED"
        private const val PEEK_LIMIT_BYTES = 16 * 1024L

        /** Pure: true for a 403 whose JSON error envelope carries PASSWORD_CHANGE_REQUIRED. */
        fun isPasswordChangeRequired(httpCode: Int, errorBody: String?): Boolean {
            if (httpCode != 403 || errorBody.isNullOrBlank()) return false
            return ApiErrorParser.parse(httpCode, errorBody).code == ERROR_CODE
        }
    }

    override fun intercept(chain: Interceptor.Chain): Response {
        val response = chain.proceed(chain.request())
        if (response.code == 403 &&
            !TokenAuthenticator.isUnauthenticatedEndpoint(chain.request().url.encodedPath)
        ) {
            val body = try { response.peekBody(PEEK_LIMIT_BYTES).string() } catch (e: Exception) { null }
            if (isPasswordChangeRequired(response.code, body)) {
                tokenManager.setPasswordChangeRequired(true)
                SessionManager.notifyPasswordChangeRequired()
            }
        }
        return response
    }
}
