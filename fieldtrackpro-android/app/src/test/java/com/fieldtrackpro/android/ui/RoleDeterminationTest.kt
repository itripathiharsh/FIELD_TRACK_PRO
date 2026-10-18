package com.fieldtrackpro.android.ui

import com.fieldtrackpro.android.utils.Roles
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** SUPER_ADMIN, ADMIN and EMPLOYEE exist; anything else falls back to EMPLOYEE and never elevates. */
class RoleDeterminationTest {

    @Test
    fun adminRolePreserved() {
        assertEquals("ADMIN", Roles.displayRole("ADMIN"))
        assertEquals("ADMIN", Roles.displayRole("admin"))
        assertEquals("ADMIN", Roles.displayRole("  Admin "))
        assertTrue(Roles.isAdmin("ADMIN"))
    }

    @Test
    fun superAdminRolePreservedAndIsAnAdmin() {
        assertEquals("SUPER_ADMIN", Roles.displayRole("SUPER_ADMIN"))
        assertEquals("SUPER_ADMIN", Roles.displayRole(" super_admin "))
        assertTrue(Roles.isAdmin("SUPER_ADMIN"))
        assertTrue(Roles.isSuperAdmin("SUPER_ADMIN"))
        assertFalse(Roles.isSuperAdmin("ADMIN"))
        assertFalse(Roles.isSuperAdmin("EMPLOYEE"))
    }

    @Test
    fun employeeRolePreserved() {
        assertEquals("EMPLOYEE", Roles.displayRole("EMPLOYEE"))
        assertFalse(Roles.isAdmin("EMPLOYEE"))
    }

    @Test
    fun managerIsNoLongerARecognizedRole() {
        assertEquals("EMPLOYEE", Roles.displayRole("MANAGER"))
        assertFalse(Roles.isAdmin("MANAGER"))
    }

    @Test
    fun unknownRolesFallBackToEmployeeAndNeverElevate() {
        assertEquals("EMPLOYEE", Roles.displayRole("REP"))
        assertEquals("EMPLOYEE", Roles.displayRole("SUPERUSER"))
        assertEquals("EMPLOYEE", Roles.displayRole("ADMINISTRATOR"))
        assertFalse(Roles.isAdmin("SUPERUSER"))
    }

    @Test
    fun missingRoleSafelyFallsBackToEmployee() {
        assertEquals("EMPLOYEE", Roles.displayRole(null))
        assertEquals("EMPLOYEE", Roles.displayRole(""))
        assertEquals("EMPLOYEE", Roles.displayRole("   "))
    }
}
