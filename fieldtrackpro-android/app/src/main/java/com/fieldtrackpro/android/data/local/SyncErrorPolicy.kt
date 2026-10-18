package com.fieldtrackpro.android.data.local

/** How a failed attempt to sync one queued offline action must be handled. */
enum class SyncErrorClass {
    /** HTTP 401: pause the whole sync, keep the queue intact. */
    AUTH_EXPIRED,

    /** Record no longer exists / not assigned to this user (HTTP 404). Never retry: surface as a conflict. */
    NOT_AVAILABLE,

    /** Network failure (no HTTP code) or 5xx: keep queued and retry with backoff. */
    RETRYABLE,

    /** Any other HTTP rejection (4xx): handled by the regular conflict detection. */
    REJECTED
}

object SyncErrorPolicy {
    const val NOT_AVAILABLE_MESSAGE =
        "This record is no longer available or is not assigned to you. The queued action was not sent."

    const val PAYMENT_NOT_AVAILABLE_MESSAGE =
        "The visit or outlet for this payment is no longer available or is not assigned to you. The payment was not recorded."

    const val UNOWNED_LEGACY_MESSAGE =
        "Unowned legacy item: saved by an older app version without an owner, so it cannot be attributed to any " +
            "employee. It was NOT synced. Review it with your manager, then discard it."

    fun classify(httpCode: Int?): SyncErrorClass = when {
        httpCode == 401 -> SyncErrorClass.AUTH_EXPIRED
        httpCode == 404 -> SyncErrorClass.NOT_AVAILABLE
        httpCode == null || httpCode >= 500 -> SyncErrorClass.RETRYABLE
        else -> SyncErrorClass.REJECTED
    }

    /**
     * 403 PASSWORD_CHANGE_REQUIRED: the account must set a new password first. Sync PAUSES (queue intact, no
     * conflict, no failure) and resumes after the change. Needs the raw error body to tell it from other 403s.
     */
    fun isPasswordChangeRequired(httpCode: Int?, errorBody: String?): Boolean =
        httpCode == 403 && com.fieldtrackpro.android.data.remote.PasswordChangeRequiredInterceptor
            .isPasswordChangeRequired(httpCode, errorBody)

    fun notAvailableConflict(action: PendingAction): SyncConflict = SyncConflict(
        pendingAction = action,
        conflictType = ConflictType.VISIT_UNAVAILABLE,
        serverStatus = null,
        message = NOT_AVAILABLE_MESSAGE
    )

    /** 408/429 are transient even though they are 4xx. */
    fun isTransient(httpCode: Int?): Boolean = httpCode == null || httpCode >= 500 || httpCode == 408 || httpCode == 429

    fun paymentNotAvailableConflict(action: PendingAction): SyncConflict = SyncConflict(
        pendingAction = action,
        conflictType = ConflictType.VISIT_UNAVAILABLE,
        serverStatus = null,
        message = PAYMENT_NOT_AVAILABLE_MESSAGE
    )

    /** 4xx rejection (400/409/422/...): keep the server's message so the user can see/fix it. */
    fun paymentRejectedConflict(action: PendingAction, httpCode: Int, serverMessage: String?): SyncConflict = SyncConflict(
        pendingAction = action,
        conflictType = ConflictType.SERVER_REJECTED,
        serverStatus = httpCode.toString(),
        message = "Payment rejected by server (HTTP $httpCode): " +
            (serverMessage?.takeIf { it.isNotBlank() } ?: "no details provided")
    )
}
