package com.fieldtrackpro.android.data.model

import com.fieldtrackpro.android.data.local.SyncConflict

/**
 * Result of syncing the offline queue.
 */
data class SyncResult(
    val syncedCount: Int,
    val conflicts: List<SyncConflict>,
    /** True when sync stopped on HTTP 401; remaining queued actions were left untouched. */
    val pausedForAuth: Boolean = false,
    /** Actions that failed for a transient reason (network/5xx) and remain queued for retry. */
    val retryableFailures: Int = 0,
    /**
     * True when sync stopped because the backend requires a forced password change
     * (403 PASSWORD_CHANGE_REQUIRED). The queue is untouched (NOT failed, NOT a conflict) and is
     * re-scheduled once the password has been changed.
     */
    val pausedForPasswordChange: Boolean = false
)
