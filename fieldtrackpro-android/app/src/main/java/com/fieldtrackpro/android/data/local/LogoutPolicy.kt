package com.fieldtrackpro.android.data.local

/** What the UI must do when the user asks to log out / delete the account. */
sealed class LogoutDecision {
    /** Nothing unsynced: log out immediately. */
    object Proceed : LogoutDecision()

    /** Unsynced items exist: ask the user (Sync now / Log out anyway / Cancel). */
    data class ConfirmUnsynced(val count: Int, val description: String) : LogoutDecision()
}

/** Result of the "Sync now" attempt made from the logout dialog. */
sealed class SyncBeforeLogoutResult {
    object AllSynced : SyncBeforeLogoutResult()
    data class StillPending(val remaining: Int, val description: String) : SyncBeforeLogoutResult()
}

/** Pure, unit-tested decision logic for the unsynced-items warning on logout / account deletion. */
object LogoutPolicy {

    fun decide(pendingForCurrentUser: List<PendingAction>): LogoutDecision =
        if (pendingForCurrentUser.isEmpty()) LogoutDecision.Proceed
        else LogoutDecision.ConfirmUnsynced(pendingForCurrentUser.size, describe(pendingForCurrentUser))

    fun afterSync(remainingForCurrentUser: List<PendingAction>): SyncBeforeLogoutResult =
        if (remainingForCurrentUser.isEmpty()) SyncBeforeLogoutResult.AllSynced
        else SyncBeforeLogoutResult.StillPending(remainingForCurrentUser.size, describe(remainingForCurrentUser))

    /** e.g. "check-ins, payments, outlet photos". */
    fun describe(items: List<PendingAction>): String =
        items.map { label(it.actionType) }.distinct().joinToString(", ")

    private fun label(actionType: String) = when (actionType) {
        "CHECK_IN" -> "check-ins"
        "CHECK_OUT" -> "check-outs"
        PendingAction.TYPE_PAYMENT_CREATE -> "payments"
        PendingAction.TYPE_OUTLET_PROOF -> "outlet photos"
        "START_DAY" -> "start-of-day records"
        "END_DAY" -> "end-of-day records"
        else -> "other actions"
    }

    fun logoutWarning(count: Int, description: String): String =
        "You have $count unsynced item${if (count == 1) "" else "s"} ($description). Sync now before logging out?"

    fun stillPendingMessage(remaining: Int): String =
        "$remaining item${if (remaining == 1) "" else "s"} could not be synced (you may be offline). " +
            "You can retry, or log out anyway."

    const val LOGOUT_ANYWAY_CONFIRMATION =
        "Your unsynced items stay saved on this device and will sync automatically when you log in again with the same account."

    const val DELETION_WARNING =
        "Warning: unsynced items will be permanently lost if you continue, because a deleted account can no longer sync them."
}
