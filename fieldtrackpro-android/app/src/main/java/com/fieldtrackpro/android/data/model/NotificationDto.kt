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
    @SerializedName("visit_id") val visitId: String?,
    @SerializedName("notification_type") val notificationType: String,
    val message: String,
    @SerializedName("is_read") val isRead: Boolean,
    @SerializedName("sent_at") val sentAt: String
)
