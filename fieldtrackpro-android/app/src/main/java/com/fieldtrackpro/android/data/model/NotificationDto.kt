package com.fieldtrackpro.android.data.model

import com.google.gson.annotations.SerializedName

/**
 * Notification DTO.
 *
 * Aligned with the API's NotificationRead schema.
 */
data class NotificationDto(
    val id: String,
    @SerializedName("user_id") val userId: String,
    @SerializedName("visit_id") val visitId: String? = null,
    @SerializedName("type") val type: String? = null,
    @SerializedName("notification_type") val legacyType: String? = null,
    val message: String,
    @SerializedName("is_read") val isRead: Boolean = false,
    @SerializedName("sent_at") val sentAt: String = ""
) {
    val notificationType: String
        get() = type ?: legacyType ?: "NEW_VISIT"

    constructor(
        id: String,
        userId: String,
        visitId: String?,
        notificationType: String,
        message: String,
        isRead: Boolean,
        sentAt: String
    ) : this(
        id = id,
        userId = userId,
        visitId = visitId,
        type = notificationType,
        legacyType = notificationType,
        message = message,
        isRead = isRead,
        sentAt = sentAt
    )
}
