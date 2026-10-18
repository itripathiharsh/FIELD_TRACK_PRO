package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.AuthApi
import com.fieldtrackpro.android.data.local.InMemorySharedPreferences
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.AccountDeletionRequest
import com.fieldtrackpro.android.data.model.AccountDeletionResponse
import com.fieldtrackpro.android.data.model.ChangePasswordRequest
import com.fieldtrackpro.android.data.model.ForgotPasswordRequest
import com.fieldtrackpro.android.data.model.ForgotPasswordResponse
import com.fieldtrackpro.android.data.model.LoginRequest
import com.fieldtrackpro.android.data.model.LoginResponse
import com.fieldtrackpro.android.data.model.MessageResponse
import com.fieldtrackpro.android.data.model.RefreshRequest
import com.fieldtrackpro.android.data.model.ResetPasswordRequest
import com.fieldtrackpro.android.data.model.UserDto
import com.fieldtrackpro.android.data.model.VerifyOtpRequest
import com.fieldtrackpro.android.utils.SessionManager
import com.google.gson.Gson
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeoutOrNull
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.Response
import java.io.IOException

class AuthRepositoryHardeningTest {

    @Before fun setUp() = SessionManager.reset()
    @After fun tearDown() = SessionManager.reset()

    private class FakeAuthApi : AuthApi {
        var deleteResponse: () -> Response<AccountDeletionResponse> = {
            Response.success(AccountDeletionResponse("DELETED", "bye"))
        }
        var changeResponse: () -> Response<LoginResponse> = { Response.success<LoginResponse>(null) }
        var loginResponse: () -> Response<LoginResponse> = {
            Response.success(LoginResponse("relogin_access", "relogin_refresh"))
        }
        var meResponse: () -> Response<UserDto> = {
            Response.success(UserDto("u1", "a@x.in", null, "Asha", "EMPLOYEE", true))
        }
        var deleteBody: AccountDeletionRequest? = null
        var changeBody: ChangePasswordRequest? = null
        var loginBodies = mutableListOf<LoginRequest>()

        override suspend fun login(request: LoginRequest): Response<LoginResponse> { loginBodies += request; return loginResponse() }
        override suspend fun refresh(request: RefreshRequest): Response<LoginResponse> = throw UnsupportedOperationException()
        override suspend fun logout(request: RefreshRequest): Response<Unit> = Response.success(Unit)
        override suspend fun getCurrentUser(): Response<UserDto> = meResponse()
        override suspend fun changePassword(request: ChangePasswordRequest): Response<LoginResponse> { changeBody = request; return changeResponse() }
        override suspend fun forgotPassword(request: ForgotPasswordRequest): Response<ForgotPasswordResponse> = throw UnsupportedOperationException()
        override suspend fun verifyOtp(request: VerifyOtpRequest): Response<MessageResponse> = throw UnsupportedOperationException()
        override suspend fun resetPassword(request: ResetPasswordRequest): Response<MessageResponse> = throw UnsupportedOperationException()
        override suspend fun deleteAccount(request: AccountDeletionRequest): Response<AccountDeletionResponse> {
            deleteBody = request
            return deleteResponse()
        }
    }

    private fun err(code: Int, body: String) =
        Response.error<AccountDeletionResponse>(code, body.toResponseBody("application/json".toMediaTypeOrNull()))

    private fun signedIn(): TokenManager = TokenManager(null, InMemorySharedPreferences()).apply {
        saveTokens("acc", "ref")
        saveUserProfile("Asha", "a@x.in", "EMPLOYEE", id = "u1")
    }

    // ------------------------------------------------------------------ account deletion

    @Test
    fun deletionBody_carriesPassword_andOptionalReason_inTheExactJsonShape() {
        val json = Gson().toJson(AccountDeletionRequest(password = "s3cret!", reason = "left company"))
        assertEquals("""{"password":"s3cret!","reason":"left company"}""", json)
        // reason is optional
        assertEquals("""{"password":"s3cret!"}""", Gson().toJson(AccountDeletionRequest(password = "s3cret!")))
    }

    @Test
    fun passwordNeverAppearsInToString() {
        val s = AccountDeletionRequest(password = "s3cret!", reason = "r").toString()
        assertFalse(s, s.contains("s3cret!"))
        assertFalse(LoginRequest(email = "a@x.in", password = "s3cret!").toString().contains("s3cret!"))
        assertFalse(ChangePasswordRequest("old-s3cret", "new-s3cret").toString().contains("s3cret"))
    }

    @Test
    fun successfulDeletion_sendsPassword_clearsSession() = runBlocking {
        val api = FakeAuthApi()
        val tm = signedIn()
        val res = AuthRepository(api, tm).requestAccountDeletion("pw-123", "  not needed  ")
        assertTrue(res is Resource.Success)
        assertEquals("pw-123", api.deleteBody?.password)
        assertEquals("not needed", api.deleteBody?.reason)
        assertNull(tm.getAccessToken())
        assertNull(tm.getRefreshToken())
    }

    @Test
    fun blankReason_isOmitted() = runBlocking {
        val api = FakeAuthApi()
        AuthRepository(api, signedIn()).requestAccountDeletion("pw", "   ")
        assertNull(api.deleteBody?.reason)
    }

    @Test
    fun wrongPassword401_mapsToInlineError_andKeepsSession() = runBlocking {
        val api = FakeAuthApi()
        api.deleteResponse = { err(401, """{"error":{"code":"AUTH_INVALID_PASSWORD","message":"Incorrect password."}}""") }
        val tm = signedIn()
        val res = AuthRepository(api, tm).requestAccountDeletion("wrong") as Resource.Error
        assertEquals(AuthRepository.INCORRECT_PASSWORD_MESSAGE, res.message)
        assertEquals("AUTH_INVALID_PASSWORD", res.errorCode)
        assertEquals("acc", tm.getAccessToken())
        assertNull(withTimeoutOrNull(200) { SessionManager.sessionExpiredEvent.first() })
    }

    @Test
    fun errorMapping_coversInvalidPasswordReauthAndOthers() {
        assertEquals(AuthRepository.INCORRECT_PASSWORD_MESSAGE,
            AuthRepository.deletionErrorMessage(403, """{"error":{"code":"REAUTH_REQUIRED","message":"x"}}"""))
        assertEquals(AuthRepository.INCORRECT_PASSWORD_MESSAGE,
            AuthRepository.deletionErrorMessage(403, """{"error":{"code":"INVALID_PASSWORD","message":"x"}}"""))
        assertEquals(AuthRepository.INCORRECT_PASSWORD_MESSAGE, AuthRepository.deletionErrorMessage(401, null))
        assertTrue(AuthRepository.deletionErrorMessage(409, """{"error":{"code":"LAST_ADMIN_CANNOT_DELETE","message":"x"}}""").contains("last active administrator"))
        assertTrue(AuthRepository.deletionErrorMessage(503, null).contains("temporarily unavailable"))
    }

    @Test
    fun networkFailureOnDeletion_keepsSession() = runBlocking {
        val api = FakeAuthApi()
        api.deleteResponse = { throw IOException("offline") }
        val tm = signedIn()
        val res = AuthRepository(api, tm).requestAccountDeletion("pw")
        assertTrue(res is Resource.Error)
        assertEquals("acc", tm.getAccessToken())
    }

    // ------------------------------------------------------------------ login + forced change

    @Test
    fun login_storesMustChangeFlag_fromLoginResponse() = runBlocking {
        val api = FakeAuthApi()
        api.loginResponse = { Response.success(LoginResponse("a", "r", mustChangePassword = true)) }
        val tm = TokenManager(null, InMemorySharedPreferences())
        val res = AuthRepository(api, tm).login("a@x.in", "pw")
        assertTrue(res is Resource.Success)
        assertTrue(tm.isPasswordChangeRequired())
    }

    @Test
    fun login_missingFlagFromOlderBackend_meansNotRequired_andClearsStaleFlag() = runBlocking {
        val api = FakeAuthApi()
        val tm = TokenManager(null, InMemorySharedPreferences())
        tm.setPasswordChangeRequired(true)
        AuthRepository(api, tm).login("a@x.in", "pw")
        assertFalse(tm.isPasswordChangeRequired())
    }

    @Test
    fun login_meResponseFlagIsAuthoritative() = runBlocking {
        val api = FakeAuthApi()
        api.meResponse = { Response.success(UserDto("u1", "a@x.in", null, "Asha", "EMPLOYEE", true, mustChangePassword = true)) }
        val tm = TokenManager(null, InMemorySharedPreferences())
        AuthRepository(api, tm).login("a@x.in", "pw")
        assertTrue(tm.isPasswordChangeRequired())
    }

    @Test
    fun login_clearsAStaleSessionExpiredEvent() = runBlocking {
        SessionManager.notifySessionExpired()
        AuthRepository(FakeAuthApi(), TokenManager(null, InMemorySharedPreferences())).login("a@x.in", "pw")
        assertNull(withTimeoutOrNull(200) { SessionManager.sessionExpiredEvent.first() })
    }

    @Test
    fun wrongLoginPassword_returnsError_withoutExpiringAnything() = runBlocking {
        val api = FakeAuthApi()
        api.loginResponse = {
            Response.error(401, """{"error":{"code":"AUTH_INVALID_CREDENTIALS","message":"Invalid credentials"}}""".toResponseBody("application/json".toMediaTypeOrNull()))
        }
        val res = AuthRepository(api, TokenManager(null, InMemorySharedPreferences())).login("a@x.in", "bad")
        assertTrue(res is Resource.Error)
        assertNull(withTimeoutOrNull(200) { SessionManager.sessionExpiredEvent.first() })
    }

    @Test
    fun deserialization_isNullSafeForAbsentMustChangeField() {
        val login = Gson().fromJson("""{"access_token":"a","refresh_token":"r","token_type":"bearer"}""", LoginResponse::class.java)
        assertNull(login.mustChangePassword)
        val me = Gson().fromJson("""{"id":"1","email":null,"mobile_number":null,"full_name":"x","role":"EMPLOYEE","is_active":true}""", UserDto::class.java)
        assertNull(me.mustChangePassword)
        val withFlag = Gson().fromJson("""{"access_token":"a","refresh_token":"r","must_change_password":true}""", LoginResponse::class.java)
        assertEquals(true, withFlag.mustChangePassword)
    }

    // ------------------------------------------------------------------ change password

    @Test
    fun changePassword_success_clearsFlag_andReLoginsBecauseBackendRevokesRefreshTokens() = runBlocking {
        val api = FakeAuthApi()
        val tm = signedIn()
        tm.setPasswordChangeRequired(true)

        val res = AuthRepository(api, tm).changePassword("old-pass", "new-pass-123")

        assertTrue(res is Resource.Success)
        assertEquals("old-pass", api.changeBody?.oldPassword)
        assertEquals("new-pass-123", api.changeBody?.newPassword)
        assertFalse(tm.isPasswordChangeRequired())
        assertEquals("a@x.in", api.loginBodies.single().email)
        assertEquals("new-pass-123", api.loginBodies.single().password)
        assertEquals("relogin_access", tm.getAccessToken())
        assertEquals("relogin_refresh", tm.getRefreshToken())
    }

    @Test
    fun changePassword_success_withTokensInBody_usesThemDirectly() = runBlocking {
        val api = FakeAuthApi()
        api.changeResponse = { Response.success(LoginResponse("body_access", "body_refresh")) }
        val tm = signedIn()
        AuthRepository(api, tm).changePassword("old-pass", "new-pass-123")
        assertEquals("body_access", tm.getAccessToken())
        assertTrue(api.loginBodies.isEmpty())
    }

    @Test
    fun changePassword_wrongCurrent_keepsFlag_andShowsMessage() = runBlocking {
        val api = FakeAuthApi()
        api.changeResponse = {
            Response.error(400, """{"error":{"code":"AUTH_WRONG_OLD_PASSWORD","message":"Old password is incorrect"}}""".toResponseBody("application/json".toMediaTypeOrNull()))
        }
        val tm = signedIn()
        tm.setPasswordChangeRequired(true)
        val res = AuthRepository(api, tm).changePassword("bad", "new-pass-123") as Resource.Error
        assertEquals("Your current password is incorrect.", res.message)
        assertTrue(tm.isPasswordChangeRequired())
    }
}
