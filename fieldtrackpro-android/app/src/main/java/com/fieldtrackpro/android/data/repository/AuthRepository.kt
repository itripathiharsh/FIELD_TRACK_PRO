package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.AuthApi
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.ForgotPasswordRequest
import com.fieldtrackpro.android.data.model.LoginRequest
import com.fieldtrackpro.android.data.model.MessageResponse
import com.fieldtrackpro.android.data.model.RefreshRequest
import com.fieldtrackpro.android.data.model.ResetPasswordRequest
import com.fieldtrackpro.android.data.model.UserDto

sealed class Resource<T> {
    data class Success<T>(val data: T) : Resource<T>()
    // isQueued distinguishes "this was saved to the offline queue for later
    // automatic sync" from a genuine server rejection - both currently
    // surface through this same Error case (differentiated only by message
    // text previously), which made them indistinguishable to a UI that
    // wants to show a calmer, non-alarming treatment for the queued case.
    data class Error<T>(val message: String, val code: Int? = null, val isQueued: Boolean = false) : Resource<T>()
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
            tokenManager.saveUserProfile(
                name = user.displayName,
                email = user.email,
                role = user.role,
                phone = user.mobileNumber,
                employeeCode = user.employeeCode,
                territoryName = user.territoryName
            )

            // Register active FCM token with backend for real push notifications
            registerFcmDeviceToken()

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
            // Unregister FCM device token before revoking credentials
            unregisterFcmDeviceToken()

            if (refreshToken != null) {
                authApi.logout(RefreshRequest(refreshToken))
            }
        } catch (e: Exception) {
            // Best effort: the local session must end regardless.
        } finally {
            tokenManager.clear()
        }
    }

    private suspend fun registerFcmDeviceToken() {
        try {
            val fcmToken = tokenManager.getFcmToken()
            if (!fcmToken.isNullOrBlank()) {
                val deviceApi = com.fieldtrackpro.android.data.remote.ApiClient.createDeviceApi(tokenManager)
                deviceApi.registerDevice(
                    com.fieldtrackpro.android.data.model.DeviceRegisterRequest(
                        fcmToken = fcmToken,
                        deviceType = "ANDROID"
                    )
                )
            }
        } catch (e: Exception) {
            // Non-fatal for auth flow
        }
    }

    private suspend fun unregisterFcmDeviceToken() {
        try {
            val fcmToken = tokenManager.getFcmToken()
            if (!fcmToken.isNullOrBlank()) {
                val deviceApi = com.fieldtrackpro.android.data.remote.ApiClient.createDeviceApi(tokenManager)
                deviceApi.unregisterDevice(
                    com.fieldtrackpro.android.data.model.DeviceUnregisterRequest(
                        fcmToken = fcmToken
                    )
                )
            }
        } catch (e: Exception) {
            // Non-fatal for logout flow
        }
    }


    suspend fun forgotPassword(email: String): Resource<String> {
        return try {
            val response = authApi.forgotPassword(ForgotPasswordRequest(email))
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!.message)
            } else {
                Resource.Error("Failed to request password reset (${response.code()})")
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    suspend fun resetPassword(email: String, otp: String, newPassword: String): Resource<String> {
        return try {
            val response = authApi.resetPassword(ResetPasswordRequest(email, otp, newPassword))
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!.message)
            } else {
                Resource.Error(if (response.code() == 400) "Invalid or expired code" else "Failed to reset password (${response.code()})")
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
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
