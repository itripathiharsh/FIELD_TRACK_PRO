package com.fieldtrackpro.android.data.local

import com.google.gson.annotations.SerializedName
import java.util.UUID

enum class ConflictType {
    STATUS_CHANGED,
    VISIT_UNAVAILABLE,
    GEO_VALIDATION_FAILED,
    SERVER_REJECTED,
    NETWORK_ERROR,
    UNOWNED_LEGACY,
    /** A persisted queue/conflict blob was unreadable; the raw data was kept under a quarantine key. */
    QUEUE_CORRUPTED
}

// @SerializedName values are the exact legacy persisted JSON field names (see PendingAction).
data class SyncConflict(
    @SerializedName("id") val id: String = UUID.randomUUID().toString(),
    @SerializedName("pendingAction") val pendingAction: PendingAction,
    @SerializedName("conflictType") val conflictType: ConflictType,
    @SerializedName("serverStatus") val serverStatus: String?,
    @SerializedName("message") val message: String,
    @SerializedName("detectedAt") val detectedAt: Long = System.currentTimeMillis()
)
