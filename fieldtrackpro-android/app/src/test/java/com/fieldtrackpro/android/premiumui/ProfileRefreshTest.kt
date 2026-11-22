package com.fieldtrackpro.android.premiumui

import com.fieldtrackpro.android.data.api.AuthApi
import com.fieldtrackpro.android.data.local.InMemorySharedPreferences
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.UserDto
import com.fieldtrackpro.android.data.repository.AuthRepository
import com.fieldtrackpro.android.data.repository.Resource
import kotlinx.coroutines.runBlocking
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.Response
import java.lang.reflect.Proxy

/** The profile screen refreshes the cached profile from GET /auth/me without ever ending the session. */
class ProfileRefreshTest {
    private fun user(id: String, code: String?) = UserDto(
        id = id, email = null, mobileNumber = "9000000000", fullName = "Neeraj", role = "EMPLOYEE", isActive = true,
        territoryName = "Kanpur", employeeCode = code
    )

    private fun repo(tm: TokenManager, me: () -> Any): AuthRepository {
        val api = Proxy.newProxyInstance(AuthApi::class.java.classLoader, arrayOf(AuthApi::class.java)) { _, m, _ ->
            when (m.name) {
                "toString" -> "stub"
                "hashCode" -> 1
                "equals" -> false
                "getCurrentUser" -> me()
                else -> throw IllegalStateException("unexpected ${m.name}")
            }
        } as AuthApi
        return AuthRepository(authApi = api, tokenManager = tm)
    }

    private fun signedIn() = TokenManager(null, InMemorySharedPreferences()).apply {
        saveTokens("a", "r")
        saveUserProfile(name = "Neeraj", email = null, role = "EMPLOYEE", id = "u1", employeeCode = null, territoryName = "Kanpur")
    }

    @Test fun newEmployeeCodeReachesTheCache() = runBlocking {
        val tm = signedIn()
        val res = repo(tm) { Response.success(user("u1", "11007")) }.refreshProfile()
        assertTrue(res is Resource.Success)
        assertEquals("11007", tm.getEmployeeCode())
    }

    @Test fun failuresKeepTheSessionAndCache() = runBlocking {
        val tm = signedIn()
        repo(tm) { Response.error<Any>(500, "{}".toResponseBody("application/json".toMediaTypeOrNull())) }.refreshProfile()
        repo(tm) { throw java.io.IOException("offline") }.refreshProfile()
        assertTrue(tm.isLoggedIn())
        assertEquals("Neeraj", tm.getUserName())
    }

    @Test fun aDifferentUsersProfileIsNeverStored() = runBlocking {
        val tm = signedIn()
        val res = repo(tm) { Response.success(user("someone-else", "11030")) }.refreshProfile()
        assertTrue(res is Resource.Error)
        assertEquals("u1", tm.getUserId())
        assertEquals(null, tm.getEmployeeCode())
    }
}
