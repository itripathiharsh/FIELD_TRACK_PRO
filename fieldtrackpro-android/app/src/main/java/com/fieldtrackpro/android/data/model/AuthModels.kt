package com.fieldtrackpro.android.data.model

import com.google.gson.annotations.SerializedName

data class LoginRequest(
    val email: String? = null,
    val mobile: String? = null,
    val password: String
)

data class LoginResponse(
    @SerializedName("access_token") val accessToken: String,
    @SerializedName("refresh_token") val refreshToken: String,
    @SerializedName("token_type") val tokenType: String = "bearer"
)

data class UserDto(
    val id: String,
    val email: String?,
    val mobile: String?,
    @SerializedName("full_name") val fullName: String,
    val role: String,
    @SerializedName("is_active") val isActive: Boolean
)
