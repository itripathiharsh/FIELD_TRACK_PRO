package com.fieldtrackpro.android.data.model

import com.google.gson.annotations.SerializedName

/**
 * Authentication DTOs.
 *
 * FT-024: these previously did not match the backend.
 *
 *  - `LoginRequest` sent `mobile`, but the API field is `mobile_number`. The
 *    server ignored the unknown key and rejected the request as "no identity
 *    supplied", so mobile login was impossible. The API now rejects unknown
 *    keys outright (extra="forbid"), which would make the old payload a hard
 *    422 rather than a confusing 401.
 *  - `UserDto` declared a non-null `full_name` that `/auth/me` did not return,
 *    and read `mobile` instead of `mobile_number`. With Gson a missing non-null
 *    field yields null and only fails later at an unrelated call site.
 *
 * Verified against the live OpenAPI schema for LoginRequest, TokenResponse and
 * CurrentUserRead.
 */

data class LoginRequest(
    val email: String? = null,
    @SerializedName("mobile_number") val mobileNumber: String? = null,
    val password: String
)

data class LoginResponse(
    @SerializedName("access_token") val accessToken: String,
    @SerializedName("refresh_token") val refreshToken: String,
    @SerializedName("token_type") val tokenType: String = "bearer"
)

/** Body of POST /api/v1/auth/refresh and /auth/logout. */
data class RefreshRequest(
    @SerializedName("refresh_token") val refreshToken: String
)

/** Response of GET /api/v1/auth/me (CurrentUserRead). */
data class UserDto(
    val id: String,
    val email: String?,
    @SerializedName("mobile_number") val mobileNumber: String?,
    @SerializedName("full_name") val fullName: String,
    val role: String,
    @SerializedName("is_active") val isActive: Boolean,
    @SerializedName("territory_id") val territoryId: String? = null,
    @SerializedName("territory_name") val territoryName: String? = null,
    @SerializedName("employee_id") val employeeId: String? = null,
    @SerializedName("employee_code") val employeeCode: String? = null
) {
    /** Display label, tolerant of an account with no employee profile. */
    val displayName: String
        get() = fullName.ifBlank { email ?: mobileNumber ?: id }
}

/** Body of PATCH /api/v1/users/me/password. */
data class ChangePasswordRequest(
    @SerializedName("old_password") val oldPassword: String,
    @SerializedName("new_password") val newPassword: String
)

data class ForgotPasswordRequest(
    val email: String
)

data class ResetPasswordRequest(
    val email: String,
    val otp: String,
    @SerializedName("new_password") val newPassword: String
)

data class MessageResponse(
    val message: String
)
