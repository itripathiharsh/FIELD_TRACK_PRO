package com.fieldtrackpro.android.data.model

import com.fieldtrackpro.android.data.local.SyncConflict

/**
 * Result of syncing the offline queue.
 */
data class SyncResult(
    val syncedCount: Int,
    val conflicts: List<SyncConflict>
)
