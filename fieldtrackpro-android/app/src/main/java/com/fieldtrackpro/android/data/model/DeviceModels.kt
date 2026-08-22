package com.fieldtrackpro.android.data.model

import com.google.gson.annotations.SerializedName

data class DeviceRegisterRequest(
    @SerializedName("fcm_token") val fcmToken: String,
    @SerializedName("device_type") val deviceType: String = "ANDROID",
    @SerializedName("device_id") val deviceId: String? = null
)

data class DeviceUnregisterRequest(
    @SerializedName("fcm_token") val fcmToken: String
)

data class DeviceDto(
    val id: String,
    @SerializedName("user_id") val userId: String,
    @SerializedName("fcm_token") val fcmToken: String,
    @SerializedName("device_type") val deviceType: String,
    @SerializedName("device_id") val deviceId: String? = null,
    @SerializedName("is_active") val isActive: Boolean = true,
    @SerializedName("created_at") val createdAt: String = "",
    @SerializedName("updated_at") val updatedAt: String = "",
    @SerializedName("last_used_at") val lastUsedAt: String? = null
)
