package com.fieldtrackpro.android.data.api

import com.fieldtrackpro.android.data.model.LoginRequest
import com.fieldtrackpro.android.data.model.LoginResponse
import com.fieldtrackpro.android.data.model.UserDto
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST

interface AuthApi {
    @POST("api/v1/auth/login")
    suspend fun login(@Body request: LoginRequest): Response<LoginResponse>

    @GET("api/v1/auth/me")
    suspend fun getCurrentUser(): Response<UserDto>
}
