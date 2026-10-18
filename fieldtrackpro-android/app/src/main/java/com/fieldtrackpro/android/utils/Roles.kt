package com.fieldtrackpro.android.utils

/**
 * The roles in the system: EMPLOYEE < ADMIN < SUPER_ADMIN (a Super Admin is a superset of Admin that can
 * also manage roles - done on the web dashboard, never in this app). Anything else (missing, blank, legacy
 * or unknown such as MANAGER/REP) is treated as EMPLOYEE - an unknown role must never elevate privileges.
 */
object Roles {
    const val SUPER_ADMIN = "SUPER_ADMIN"
    const val ADMIN = "ADMIN"
    const val EMPLOYEE = "EMPLOYEE"

    fun displayRole(storedRole: String?): String {
        val role = storedRole?.trim()
        return when {
            role.equals(SUPER_ADMIN, ignoreCase = true) -> SUPER_ADMIN
            role.equals(ADMIN, ignoreCase = true) -> ADMIN
            else -> EMPLOYEE
        }
    }

    /** True for ADMIN and SUPER_ADMIN (global-access roles). */
    fun isAdmin(storedRole: String?): Boolean = displayRole(storedRole) != EMPLOYEE

    fun isSuperAdmin(storedRole: String?): Boolean = displayRole(storedRole) == SUPER_ADMIN
}
