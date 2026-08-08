package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.AuthApi
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.LoginRequest
import com.fieldtrackpro.android.data.model.UserDto

sealed class Resource<T> {
    data class Success<T>(val data: T) : Resource<T>()
    data class Error<T>(val message: String, val code: Int? = null) : Resource<T>()
    class Loading<T> : Resource<T>()
}

class AuthRepository(
    private val authApi: AuthApi,
    private val tokenManager: TokenManager
) {
    suspend fun login(identity: String, password: String): Resource<UserDto> {
        return try {
            val isEmail = identity.contains("@")
            val req = LoginRequest(
                email = if (isEmail) identity else null,
                mobile = if (!isEmail) identity else null,
                password = password
            )
            val response = authApi.login(req)
            if (response.isSuccessful && response.body() != null) {
                val tokens = response.body()!!
                tokenManager.saveTokens(tokens.accessToken, tokens.refreshToken)

                // Fetch current user details
                val meResponse = authApi.getCurrentUser()
                if (meResponse.isSuccessful && meResponse.body() != null) {
                    val user = meResponse.body()!!
                    tokenManager.saveUserProfile(user.fullName, user.email, user.role)
                    Resource.Success(user)
                } else {
                    Resource.Error("Login succeeded but failed to fetch profile.")
                }
            } else {
                Resource.Error("Invalid credentials or authentication error (${response.code()})", response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage ?: "Connection failed"}")
        }
    }

    fun logout() {
        tokenManager.clear()
    }

    fun isLoggedIn(): Boolean = tokenManager.isLoggedIn()
}
