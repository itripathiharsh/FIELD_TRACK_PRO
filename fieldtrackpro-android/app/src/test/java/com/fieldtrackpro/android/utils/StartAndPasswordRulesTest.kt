package com.fieldtrackpro.android.utils

import com.fieldtrackpro.android.data.local.InMemorySharedPreferences
import com.fieldtrackpro.android.data.local.TokenManager
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class StartAndPasswordRulesTest {

    // ------------------------------------------------------------------ cold-start routing (no network)

    @Test
    fun storedSession_opensDashboard_withoutAnyNetworkCall() {
        val tm = TokenManager(null, InMemorySharedPreferences())
        tm.saveTokens("access", "refresh")
        tm.saveUserProfile("Asha", "a@x.in", "EMPLOYEE", id = "u1")
        assertEquals(StartDestination.DASHBOARD, StartRouting.decide(tm))
    }

    @Test
    fun noSession_opensLogin() {
        assertEquals(StartDestination.LOGIN, StartRouting.decide(TokenManager(null, InMemorySharedPreferences())))
    }

    @Test
    fun tokensWithoutProfile_orWithoutRefreshToken_openLogin() {
        val onlyTokens = TokenManager(null, InMemorySharedPreferences()).apply { saveTokens("a", "r") }
        assertEquals(StartDestination.LOGIN, StartRouting.decide(onlyTokens))
        assertEquals(StartDestination.LOGIN, StartRouting.decide(true, false, true, false))
    }

    @Test
    fun pendingPasswordChange_opensTheForcedScreen() {
        val tm = TokenManager(null, InMemorySharedPreferences())
        tm.saveTokens("access", "refresh")
        tm.saveUserProfile("Asha", null, "EMPLOYEE", id = "u1")
        tm.setPasswordChangeRequired(true)
        assertEquals(StartDestination.CHANGE_PASSWORD, StartRouting.decide(tm))
    }

    @Test
    fun logoutAfterPasswordPending_returnsToLogin() {
        val tm = TokenManager(null, InMemorySharedPreferences())
        tm.saveTokens("access", "refresh")
        tm.saveUserProfile("Asha", null, "EMPLOYEE", id = "u1")
        tm.setPasswordChangeRequired(true)
        tm.clear()
        assertEquals(StartDestination.LOGIN, StartRouting.decide(tm))
    }

    // ------------------------------------------------------------------ password rules

    @Test
    fun validPassword_passes() {
        assertNull(PasswordRules.validate("oldpass1", "NewPass#2026", "NewPass#2026"))
    }

    @Test
    fun minimumLength_is8() {
        assertEquals(PasswordRules.Issue.TOO_SHORT, PasswordRules.validate("old", "1234567", "1234567"))
        assertNull(PasswordRules.validate("old", "12345678", "12345678"))
    }

    @Test
    fun maximum_is72Utf8Bytes_notCharacters() {
        val ascii72 = "a".repeat(72)
        val ascii73 = "a".repeat(73)
        assertNull(PasswordRules.validate("old", ascii72, ascii72))
        assertEquals(PasswordRules.Issue.TOO_LONG, PasswordRules.validate("old", ascii73, ascii73))
        // 40 two-byte characters = 80 bytes: only 40 chars but over the byte limit
        val twoByte = "é".repeat(40)
        assertEquals(80, PasswordRules.utf8Bytes(twoByte))
        assertEquals(PasswordRules.Issue.TOO_LONG, PasswordRules.validate("old", twoByte, twoByte))
        // 36 two-byte characters = exactly 72 bytes: allowed
        val ok = "é".repeat(36)
        assertNull(PasswordRules.validate("old", ok, ok))
    }

    @Test
    fun mustDifferFromCurrent() {
        assertEquals(PasswordRules.Issue.SAME_AS_CURRENT, PasswordRules.validate("samepass1", "samepass1", "samepass1"))
    }

    @Test
    fun confirmationMustMatch_andCurrentIsRequired() {
        assertEquals(PasswordRules.Issue.MISMATCH, PasswordRules.validate("old", "newpass123", "newpass124"))
        assertEquals(PasswordRules.Issue.CURRENT_EMPTY, PasswordRules.validate("", "newpass123", "newpass123"))
    }
}
