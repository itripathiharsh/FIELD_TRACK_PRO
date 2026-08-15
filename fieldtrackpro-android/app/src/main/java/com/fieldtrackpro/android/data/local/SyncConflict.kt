package com.fieldtrackpro.android.data.local

import java.util.UUID

enum class ConflictType {
    STATUS_CHANGED,
    VISIT_UNAVAILABLE,
    GEO_VALIDATION_FAILED,
    SERVER_REJECTED,
    NETWORK_ERROR
}

data class SyncConflict(
    val id: String = UUID.randomUUID().toString(),
    val pendingAction: PendingAction,
    val conflictType: ConflictType,
    val serverStatus: String?,
    val message: String,
    val detectedAt: Long = System.currentTimeMillis()
)
