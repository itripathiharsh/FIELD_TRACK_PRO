package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.AuthApi
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.AccountDeletionRequest
import com.fieldtrackpro.android.data.model.ChangePasswordRequest
import com.fieldtrackpro.android.data.model.AccountDeletionResponse
import com.fieldtrackpro.android.data.model.ForgotPasswordRequest
import com.fieldtrackpro.android.data.model.LoginRequest
import com.fieldtrackpro.android.data.model.MessageResponse
import com.fieldtrackpro.android.data.model.RefreshRequest
import com.fieldtrackpro.android.data.model.ResetPasswordRequest
import com.fieldtrackpro.android.data.model.UserDto

import com.fieldtrackpro.android.data.remote.ApiError
import com.fieldtrackpro.android.data.remote.ApiErrorParser
import com.fieldtrackpro.android.data.remote.TokenAuthenticator
import com.fieldtrackpro.android.utils.SessionManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

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
            val tokens = response.body()
            if (!response.isSuccessful || tokens == null) {
                tokenManager.clear()
                val errBody = response.errorBody()?.string()
                return Resource.Error(messageForStatus(response.code(), errBody), response.code())
            }

            // commit() writes (durable) - keep that disk I/O off the main thread (this suspend fun is called from it).
            withContext(Dispatchers.IO) { tokenManager.saveTokens(tokens.accessToken, tokens.refreshToken) }
            // A fresh sign-in supersedes any never-consumed "session expired" event from the previous session.
            SessionManager.clearPendingEvents()
            tokenManager.setPasswordChangeRequired(tokens.mustChangePassword == true)

            val meResponse = authApi.getCurrentUser()
            val user = meResponse.body()
            if (!meResponse.isSuccessful || user == null) {
                tokenManager.clear()
                return Resource.Error("Signed in, but the profile could not be loaded.")
            }

            withContext(Dispatchers.IO) { tokenManager.saveUserProfile(
                id = user.id,
                name = user.displayName,
                email = user.email,
                role = user.role,
                phone = user.mobileNumber,
                employeeCode = user.employeeCode,
                territoryName = user.territoryName
            ) }

            if (user.mustChangePassword != null) tokenManager.setPasswordChangeRequired(user.mustChangePassword)

            // Register active FCM token with backend for real push notifications (not while a forced
            // password change is pending: every such call would 403).
            if (!tokenManager.isPasswordChangeRequired()) registerFcmDeviceToken()

            Resource.Success(user)
        } catch (e: Exception) {
            tokenManager.clear()
            Resource.Error(
                when (e) {
                    is java.net.UnknownHostException, is java.net.ConnectException, is java.net.SocketTimeoutException, is java.io.IOException ->
                        "Can't reach the server. Check your internet connection and try again."
                    else -> "Sign-in could not be completed. Please try again."
                }
            )
        }
    }

    /**
     * Best-effort refresh of the cached profile from GET /auth/me (existing endpoint, unchanged contract). The profile
     * used to be cached only at sign-in, so a code or territory set later by an admin never reached the app.
     * Never ends the session: any failure just keeps the cached profile. Only updates the SAME signed-in user.
     */
    suspend fun refreshProfile(): Resource<UserDto> {
        return try {
            val response = authApi.getCurrentUser()
            val user = response.body()
            if (!response.isSuccessful || user == null) return Resource.Error("Profile not refreshed (${response.code()})", response.code())
            val currentId = tokenManager.getUserId()
            if (currentId != null && currentId != user.id) return Resource.Error("Profile belongs to a different session")
            withContext(Dispatchers.IO) {
                tokenManager.saveUserProfile(
                    id = user.id,
                    name = user.displayName,
                    email = user.email,
                    role = user.role,
                    phone = user.mobileNumber,
                    employeeCode = user.employeeCode,
                    territoryName = user.territoryName
                )
            }
            Resource.Success(user)
        } catch (e: Exception) {
            if (e is kotlinx.coroutines.CancellationException) throw e
            Resource.Error("Profile not refreshed: ${e.javaClass.simpleName}")
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
            val body = response.body()
            if (response.isSuccessful && body != null) {
                Resource.Success(body)
            } else {
                Resource.Error(com.fieldtrackpro.android.data.remote.HttpErrors.message(response.code(), "Failed to request password reset (${response.code()})"))
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    suspend fun verifyOtp(identifier: String, otp: String): Resource<String> {
        return try {
            val response = authApi.verifyOtp(com.fieldtrackpro.android.data.model.VerifyOtpRequest(identifier = identifier, otp = otp))
            val body = response.body()
            if (response.isSuccessful && body != null) {
                Resource.Success(body.message)
            } else {
                Resource.Error(if (response.code() == 400) "Invalid or expired verification code" else com.fieldtrackpro.android.data.remote.HttpErrors.message(response.code(), "Verification failed (${response.code()})"))
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    suspend fun resetPassword(identifier: String, otp: String, newPassword: String): Resource<String> {
        return try {
            val response = authApi.resetPassword(ResetPasswordRequest(identifier = identifier, otp = otp, newPassword = newPassword))
            val body = response.body()
            if (response.isSuccessful && body != null) {
                Resource.Success(body.message)
            } else {
                Resource.Error(if (response.code() == 400) "Invalid or expired verification code" else com.fieldtrackpro.android.data.remote.HttpErrors.message(response.code(), "Failed to reset password (${response.code()})"))
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    /**
     * Play account-deletion requirement: DELETE /api/v1/auth/me with the CURRENT PASSWORD (re-authentication;
     * the backend rejects a body without it) and an optional reason. On success the local session is cleared;
     * the caller then wipes all remaining local user data (see AccountDataWiper) and navigates to login.
     * The password is only ever placed in the request body: never logged, never kept.
     */
    suspend fun requestAccountDeletion(password: String, reason: String? = null): Resource<AccountDeletionResponse> {
        return try {
            val trimmed = reason?.trim()?.takeIf { it.isNotEmpty() }
            val response = authApi.deleteAccount(AccountDeletionRequest(password = password, reason = trimmed))
            val body = response.body()
            if (response.isSuccessful) {
                tokenManager.clear()
                Resource.Success(body ?: AccountDeletionResponse(status = "DELETED", message = "Account deleted."))
            } else {
                val errBody = try { response.errorBody()?.string() } catch (e: Exception) { null }
                Resource.Error(
                    deletionErrorMessage(response.code(), errBody),
                    response.code(),
                    errorCode = ApiErrorParser.parse(response.code(), errBody).code
                )
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage ?: "Connection failed"}")
        }
    }

    /**
     * Forced / voluntary password change. On success the "must change" flag is cleared. The backend revokes
     * every refresh token of the user on a password change, so unless the response already carries a new token
     * pair we silently sign in again with the new password to get a working session.
     */
    suspend fun changePassword(currentPassword: String, newPassword: String): Resource<Unit> {
        return try {
            val response = authApi.changePassword(ChangePasswordRequest(currentPassword, newPassword))
            if (!response.isSuccessful) {
                val errBody = try { response.errorBody()?.string() } catch (e: Exception) { null }
                return Resource.Error(
                    changePasswordErrorMessage(response.code(), errBody),
                    response.code(),
                    errorCode = ApiErrorParser.parse(response.code(), errBody).code
                )
            }
            val newTokens = response.body()
            if (newTokens != null && newTokens.accessToken.isNotBlank() && newTokens.refreshToken.isNotBlank()) {
                tokenManager.saveTokens(newTokens.accessToken, newTokens.refreshToken)
            } else {
                reLoginAfterPasswordChange(newPassword)
            }
            tokenManager.setPasswordChangeRequired(false)
            Resource.Success(Unit)
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage ?: "Connection failed"}")
        }
    }

    private suspend fun reLoginAfterPasswordChange(newPassword: String) {
        try {
            val email = tokenManager.getUserEmail()
            val phone = tokenManager.getUserPhone()
            if (email.isNullOrBlank() && phone.isNullOrBlank()) return
            val response = authApi.login(
                LoginRequest(
                    email = email?.takeIf { it.isNotBlank() },
                    mobileNumber = if (email.isNullOrBlank()) phone else null,
                    password = newPassword
                )
            )
            val tokens = response.body()
            if (response.isSuccessful && tokens != null) {
                tokenManager.saveTokens(tokens.accessToken, tokens.refreshToken)
            }
        } catch (e: Exception) {
            // Best effort: the password HAS changed. If this fails the next refresh is rejected and the user signs in.
        }
    }

    fun isLoggedIn(): Boolean = tokenManager.isLoggedIn()

    companion object {
        const val INCORRECT_PASSWORD_MESSAGE = "Incorrect password. Please check it and try again."

        /** 401/403 with INVALID_PASSWORD / REAUTH_REQUIRED (or a bare 401/403) => inline "incorrect password". */
        fun deletionErrorMessage(httpCode: Int, errorBody: String?): String {
            val code = ApiErrorParser.parse(httpCode, errorBody).code
            return when {
                (httpCode == 401 || httpCode == 403) && (code in TokenAuthenticator.PASSWORD_FAILURE_CODES) ->
                    INCORRECT_PASSWORD_MESSAGE
                httpCode == 409 && code == "LAST_ADMIN_CANNOT_DELETE" ->
                    "You are the last active administrator, so this account cannot be deleted."
                httpCode == 409 && code == "ACCOUNT_ALREADY_INACTIVE" -> "This account has already been deleted."
                httpCode == 401 || httpCode == 403 -> INCORRECT_PASSWORD_MESSAGE
                httpCode == 429 -> "Too many attempts. Please wait and try again."
                httpCode >= 500 -> "Server is temporarily unavailable. Please try again shortly."
                else -> com.fieldtrackpro.android.data.remote.HttpErrors.message(httpCode, "Could not delete the account (error $httpCode).")
            }
        }

        fun changePasswordErrorMessage(httpCode: Int, errorBody: String?): String {
            val code = ApiErrorParser.parse(httpCode, errorBody).code
            return when {
                code == "AUTH_WRONG_OLD_PASSWORD" -> "Your current password is incorrect."
                code == "AUTH_PASSWORD_UNCHANGED" -> "New password must be different from the current password."
                httpCode == 422 -> "That password was not accepted. Use 8 to 72 characters."
                httpCode == 429 -> "Too many attempts. Please wait and try again."
                httpCode >= 500 -> "Server is temporarily unavailable. Please try again shortly."
                else -> "Could not change the password (error $httpCode)."
            }
        }
    }

    private fun messageForStatus(code: Int, errorBody: String? = null): String {
        if (!errorBody.isNullOrBlank()) {
            val lower = errorBody.lowercase()
            // Admin-issued temporary password past its expiry (only returned after the password itself was correct).
            if (lower.contains("auth_temp_password_expired")) {
                return "Your temporary password has expired. Ask your administrator to reset it again."
            }
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
