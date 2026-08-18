package com.fieldtrackpro.android.data.api

import com.fieldtrackpro.android.data.model.ChangePasswordRequest
import com.fieldtrackpro.android.data.model.ForgotPasswordRequest
import com.fieldtrackpro.android.data.model.LoginRequest
import com.fieldtrackpro.android.data.model.LoginResponse
import com.fieldtrackpro.android.data.model.MessageResponse
import com.fieldtrackpro.android.data.model.RefreshRequest
import com.fieldtrackpro.android.data.model.ResetPasswordRequest
import com.fieldtrackpro.android.data.model.UserDto
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.PATCH
import retrofit2.http.POST

/**
 * Authentication endpoints.
 *
 * The refresh and logout routes were missing from this interface even though
 * the backend has always exposed them, so the app could neither recover from a
 * 15-minute access-token expiry nor revoke its session on sign-out - the
 * Android equivalents of FT-008 and FT-009.
 */
interface AuthApi {
    @POST("api/v1/auth/login")
    suspend fun login(@Body request: LoginRequest): Response<LoginResponse>

    @POST("api/v1/auth/refresh")
    suspend fun refresh(@Body request: RefreshRequest): Response<LoginResponse>

    @POST("api/v1/auth/logout")
    suspend fun logout(@Body request: RefreshRequest): Response<Unit>

    @GET("api/v1/auth/me")
    suspend fun getCurrentUser(): Response<UserDto>

    @PATCH("api/v1/users/me/password")
    suspend fun changePassword(@Body request: ChangePasswordRequest): Response<Unit>

    @POST("api/v1/auth/forgot-password")
    suspend fun forgotPassword(@Body request: ForgotPasswordRequest): Response<MessageResponse>

    @POST("api/v1/auth/reset-password")
    suspend fun resetPassword(@Body request: ResetPasswordRequest): Response<MessageResponse>
}
