package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.AuthApi
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.ForgotPasswordRequest
import com.fieldtrackpro.android.data.model.LoginRequest
import com.fieldtrackpro.android.data.model.MessageResponse
import com.fieldtrackpro.android.data.model.RefreshRequest
import com.fieldtrackpro.android.data.model.ResetPasswordRequest
import com.fieldtrackpro.android.data.model.UserDto

import com.fieldtrackpro.android.data.remote.ApiError

sealed class Resource<T> {
    data class Success<T>(val data: T) : Resource<T>()
    data class Error<T>(
        val message: String,
        val code: Int? = null,
        val errorCode: String? = null,
        val apiError: ApiError? = null,
        val isQueued: Boolean = false
    ) : Resource<T>()
    class Loading<T> : Resource<T>()
}

/**
 * Authentication repository.
 *
 * APP-AUTH-001 & APP-AUTH-005: Clean session management and user-friendly error messages.
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
                val errBody = response.errorBody()?.string()
                return Resource.Error(messageForStatus(response.code(), errBody), response.code())
            }

            val tokens = response.body()!!
            tokenManager.saveTokens(tokens.accessToken, tokens.refreshToken)

            val meResponse = authApi.getCurrentUser()
            if (!meResponse.isSuccessful || meResponse.body() == null) {
                tokenManager.clear()
                return Resource.Error("Signed in, but the profile could not be loaded.")
            }

            val user = meResponse.body()!!
            tokenManager.saveUserProfile(
                id = user.id,
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

    suspend fun logout() {
        val refreshToken = tokenManager.getRefreshToken()
        try {
            unregisterFcmDeviceToken()
            if (refreshToken != null) {
                authApi.logout(RefreshRequest(refreshToken))
            }
        } catch (e: Exception) {
            // Best effort
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

    suspend fun forgotPassword(identifier: String): Resource<com.fieldtrackpro.android.data.model.ForgotPasswordResponse> {
        return try {
            val response = authApi.forgotPassword(ForgotPasswordRequest(identifier = identifier))
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Failed to request password reset (${response.code()})")
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    suspend fun verifyOtp(identifier: String, otp: String): Resource<String> {
        return try {
            val response = authApi.verifyOtp(com.fieldtrackpro.android.data.model.VerifyOtpRequest(identifier = identifier, otp = otp))
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!.message)
            } else {
                Resource.Error(if (response.code() == 400) "Invalid or expired verification code" else "Verification failed (${response.code()})")
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    suspend fun resetPassword(identifier: String, otp: String, newPassword: String): Resource<String> {
        return try {
            val response = authApi.resetPassword(ResetPasswordRequest(identifier = identifier, otp = otp, newPassword = newPassword))
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!.message)
            } else {
                Resource.Error(if (response.code() == 400) "Invalid or expired verification code" else "Failed to reset password (${response.code()})")
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    fun isLoggedIn(): Boolean = tokenManager.isLoggedIn()

    private fun messageForStatus(code: Int, errorBody: String? = null): String {
        if (!errorBody.isNullOrBlank()) {
            val lower = errorBody.lowercase()
            if (lower.contains("disabled") || lower.contains("inactive")) {
                return "This account is disabled. Contact your administrator."
            }
            if (lower.contains("invalid") || lower.contains("credential") || lower.contains("password")) {
                return "Incorrect email/mobile or password."
            }
        }
        return when (code) {
            400 -> "Invalid login request. Please verify your credentials."
            401 -> "Incorrect email/mobile or password."
            403 -> "This account is disabled. Contact your administrator."
            429 -> "Too many sign-in attempts. Please wait and try again."
            500, 502, 503, 504 -> "Server is temporarily unavailable. Please try again shortly."
            else -> "Sign-in failed (error $code)."
        }
    }
}
