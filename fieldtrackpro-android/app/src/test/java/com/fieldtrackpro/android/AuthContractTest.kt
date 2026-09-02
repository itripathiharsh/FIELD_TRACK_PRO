package com.fieldtrackpro.android

import com.fieldtrackpro.android.data.model.LoginRequest
import com.fieldtrackpro.android.data.model.RefreshRequest
import com.google.gson.Gson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class AuthContractTest {

    private val gson = Gson()

    @Test
    fun loginRequest_emailLogin_serializesCorrectly() {
        val request = LoginRequest(
            email = "test@example.com",
            mobileNumber = null,
            password = "securePassword123"
        )
        val json = gson.toJson(request)
        assertTrue("Should contain email", json.contains("\"email\":\"test@example.com\""))
        assertTrue("Should contain password", json.contains("\"password\":\"securePassword123\""))
        assertTrue("Should NOT contain 'mobile' field", !json.contains("\"mobile\""))
    }

    @Test
    fun loginRequest_mobileLogin_serializesCorrectly() {
        val request = LoginRequest(
            email = null,
            mobileNumber = "9876543210",
            password = "securePassword123"
        )
        val json = gson.toJson(request)
        assertTrue("Should contain mobile_number", json.contains("\"mobile_number\":\"9876543210\""))
        assertTrue("Should contain password", json.contains("\"password\":\"securePassword123\""))
        assertTrue("Should NOT contain 'mobile' field", !json.contains("\"mobile\""))
    }

    @Test
    fun refreshRequest_serializesCorrectly() {
        val request = RefreshRequest(refreshToken = "some-refresh-token")
        val json = gson.toJson(request)
        assertTrue("Should contain refresh_token", json.contains("\"refresh_token\":\"some-refresh-token\""))
    }

    @Test
    fun loginRequest_noFallbackFields() {
        val request = LoginRequest(
            email = "test@example.com",
            mobileNumber = null,
            password = "password"
        )
        val json = gson.toJson(request)
        assertTrue("Should contain email", json.contains("\"email\""))
        assertTrue("Should contain password", json.contains("\"password\""))
        assertTrue("Should NOT contain 'mobile' field", !json.contains("\"mobile\""))
        assertTrue("Should NOT contain 'full_name' field", !json.contains("\"full_name\""))
    }

    @Test
    fun forgotPasswordRequest_identifier_serializesCorrectly() {
        val request = com.fieldtrackpro.android.data.model.ForgotPasswordRequest(identifier = "9876543210")
        val json = gson.toJson(request)
        assertTrue("Should contain identifier", json.contains("\"identifier\":\"9876543210\""))
    }

    @Test
    fun verifyOtpRequest_serializesCorrectly() {
        val request = com.fieldtrackpro.android.data.model.VerifyOtpRequest(identifier = "user@example.com", otp = "123456")
        val json = gson.toJson(request)
        assertTrue("Should contain identifier", json.contains("\"identifier\":\"user@example.com\""))
        assertTrue("Should contain otp", json.contains("\"otp\":\"123456\""))
    }

    @Test
    fun resetPasswordRequest_serializesCorrectly() {
        val request = com.fieldtrackpro.android.data.model.ResetPasswordRequest(
            identifier = "user@example.com",
            otp = "123456",
            newPassword = "NewPassword123!"
        )
        val json = gson.toJson(request)
        assertTrue("Should contain identifier", json.contains("\"identifier\":\"user@example.com\""))
        assertTrue("Should contain otp", json.contains("\"otp\":\"123456\""))
        assertTrue("Should contain new_password", json.contains("\"new_password\":\"NewPassword123!\""))
    }
}
