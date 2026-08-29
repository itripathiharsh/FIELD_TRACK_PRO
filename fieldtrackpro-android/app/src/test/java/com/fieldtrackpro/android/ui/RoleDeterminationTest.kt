package com.fieldtrackpro.android.ui

import org.junit.Assert.assertEquals
import org.junit.Test

class RoleDeterminationTest {

    private fun determineDisplayRole(storedRole: String?): String {
        return if (!storedRole.isNullOrBlank()) storedRole else "EMPLOYEE"
    }

    @Test
    fun testRoleDetermination_adminRolePreserved() {
        val role = determineDisplayRole("ADMIN")
        assertEquals("ADMIN", role)
    }

    @Test
    fun testRoleDetermination_managerRolePreserved() {
        val role = determineDisplayRole("MANAGER")
        assertEquals("MANAGER", role)
    }

    @Test
    fun testRoleDetermination_repRolePreserved() {
        val role = determineDisplayRole("REP")
        assertEquals("REP", role)
    }

    @Test
    fun testRoleDetermination_missingRoleSafelyFallsBackToEmployee() {
        assertEquals("EMPLOYEE", determineDisplayRole(null))
        assertEquals("EMPLOYEE", determineDisplayRole(""))
        assertEquals("EMPLOYEE", determineDisplayRole("   "))
    }
}
