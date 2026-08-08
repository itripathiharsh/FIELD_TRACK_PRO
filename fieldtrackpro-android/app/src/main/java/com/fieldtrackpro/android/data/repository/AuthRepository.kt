package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.AuthApi
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.LoginRequest
import com.fieldtrackpro.android.data.model.RefreshRequest
import com.fieldtrackpro.android.data.model.UserDto

sealed class Resource<T> {
    data class Success<T>(val data: T) : Resource<T>()
    data class Error<T>(val message: String, val code: Int? = null) : Resource<T>()
    class Loading<T> : Resource<T>()
}

/**
 * Authentication repository.
 *
 * FT-024: the login payload now sends `mobile_number`, matching the API. The
 * backend rejects unknown keys, so the previous `mobile` field would fail
 * outright rather than being silently discarded.
 *
 * A failed login leaves NO session behind - the Android counterpart of the
 * FT-001 rule. There is no fabricated user and no guessed role anywhere in
 * this class; identity comes from `/auth/me` or the sign-in does not succeed.
 */
class AuthRepository(
    private val authApi: AuthApi,
    private val tokenManager: TokenManager
) {

    suspend fun login(identity: String, password: String): Resource<UserDto> {
        return try {
            val isEmail = identity.contains("@")
            val request = LoginRequest(
                email = if (isEmail) identity else null,
                mobileNumber = if (isEmail) null else identity,
                password = password
            )

            val response = authApi.login(request)
            if (!response.isSuccessful || response.body() == null) {
                tokenManager.clear()
                return Resource.Error(messageForStatus(response.code()), response.code())
            }

            val tokens = response.body()!!
            tokenManager.saveTokens(tokens.accessToken, tokens.refreshToken)

            val meResponse = authApi.getCurrentUser()
            if (!meResponse.isSuccessful || meResponse.body() == null) {
                // Half a session is no session: discard the tokens.
                tokenManager.clear()
                return Resource.Error("Signed in, but the profile could not be loaded.")
            }

            val user = meResponse.body()!!
            tokenManager.saveUserProfile(user.displayName, user.email, user.role)
            Resource.Success(user)
        } catch (e: Exception) {
            tokenManager.clear()
            Resource.Error("Network error: ${e.localizedMessage ?: "Connection failed"}")
        }
    }

    /**
     * Exchange the refresh token for a fresh pair.
     *
     * Returns false when the session is genuinely over, in which case stored
     * credentials are cleared so the app cannot keep retrying a dead token.
     */
    suspend fun refreshSession(): Boolean {
        val refreshToken = tokenManager.getRefreshToken() ?: return false
        return try {
            val response = authApi.refresh(RefreshRequest(refreshToken))
            val body = response.body()
            if (response.isSuccessful && body != null) {
                tokenManager.saveTokens(body.accessToken, body.refreshToken)
                true
            } else {
                tokenManager.clear()
                false
            }
        } catch (e: Exception) {
            false
        }
    }

    /**
     * Sign out.
     *
     * The refresh token is revoked server-side before local state is cleared,
     * so the session cannot be resumed from a copied token. Local credentials
     * are cleared even if the network call fails.
     */
    suspend fun logout() {
        val refreshToken = tokenManager.getRefreshToken()
        try {
            if (refreshToken != null) {
                authApi.logout(RefreshRequest(refreshToken))
            }
        } catch (e: Exception) {
            // Best effort: the local session must end regardless.
        } finally {
            tokenManager.clear()
        }
    }

    fun isLoggedIn(): Boolean = tokenManager.isLoggedIn()

    private fun messageForStatus(code: Int): String = when (code) {
        401 -> "Incorrect email/mobile or password."
        403 -> "This account is disabled. Contact your administrator."
        429 -> "Too many sign-in attempts. Please wait and try again."
        else -> "Sign-in failed (error $code)."
    }
}
