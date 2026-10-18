package com.fieldtrackpro.android.utils

/**
 * Client-side rules for choosing a new password (forced change screen). They mirror the backend so the user gets
 * instant feedback: minimum 8 characters, at most 72 UTF-8 BYTES (bcrypt silently ignores anything beyond 72 bytes,
 * so non-ASCII passwords hit the limit sooner than 72 characters), different from the current password.
 */
object PasswordRules {
    const val MIN_LENGTH = 8
    const val MAX_BYTES = 72

    enum class Issue(val message: String) {
        CURRENT_EMPTY("Enter your current password."),
        TOO_SHORT("New password must be at least $MIN_LENGTH characters."),
        TOO_LONG("New password is too long (at most $MAX_BYTES bytes; accented or non-English characters count extra)."),
        SAME_AS_CURRENT("New password must be different from the current password."),
        MISMATCH("New password and confirmation do not match.")
    }

    fun utf8Bytes(value: String): Int = value.toByteArray(Charsets.UTF_8).size

    /** First problem found, or null when the three fields are acceptable. Order: current, length, bytes, same, confirm. */
    fun validate(current: String, new: String, confirm: String): Issue? = when {
        current.isEmpty() -> Issue.CURRENT_EMPTY
        new.length < MIN_LENGTH -> Issue.TOO_SHORT
        utf8Bytes(new) > MAX_BYTES -> Issue.TOO_LONG
        new == current -> Issue.SAME_AS_CURRENT
        new != confirm -> Issue.MISMATCH
        else -> null
    }
}
