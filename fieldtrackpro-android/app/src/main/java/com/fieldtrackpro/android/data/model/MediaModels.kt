package com.fieldtrackpro.android.data.model

import com.google.gson.annotations.SerializedName

/**
 * Media DTO.
 *
 * Aligned with the API's MediaRead, including the FT-036 integrity fields.
 * `mediaType` is the enum PHOTO | DOCUMENT - never a MIME string.
 */
data class MediaDto(
    val id: String,
    @SerializedName("visit_id") val visitId: String,
    @SerializedName("media_type") val mediaType: String,
    @SerializedName("storage_key") val storageKey: String,
    @SerializedName("file_size_bytes") val fileSizeBytes: Long,
    @SerializedName("checksum_sha256") val checksumSha256: String? = null,
    @SerializedName("original_filename") val originalFilename: String? = null,
    @SerializedName("uploaded_by") val uploadedBy: String? = null,
    @SerializedName("uploaded_at") val uploadedAt: String
) {
    val isPhoto: Boolean get() = mediaType == "PHOTO"
    val isDocument: Boolean get() = mediaType == "DOCUMENT"

    /** Name to show in the UI; falls back to the storage key's last segment. */
    val displayName: String
        get() = originalFilename ?: storageKey.substringAfterLast('/')
}
