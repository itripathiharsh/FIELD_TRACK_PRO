package com.fieldtrackpro.android.data.model

import com.google.gson.annotations.SerializedName

data class MediaDto(
    val id: String,
    @SerializedName("visit_id") val visitId: String,
    @SerializedName("media_type") val mediaType: String,
    @SerializedName("storage_key") val storageKey: String,
    @SerializedName("file_size_bytes") val fileSizeBytes: Long,
    @SerializedName("uploaded_at") val uploadedAt: String
)
