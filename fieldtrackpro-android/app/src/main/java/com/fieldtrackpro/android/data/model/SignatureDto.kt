package com.fieldtrackpro.android.data.model

import com.google.gson.annotations.SerializedName

/**
 * Signature DTO.
 *
 * Aligned with the API's SignatureRead schema.
 */
data class SignatureDto(
    val id: String,
    @SerializedName("visit_id") val visitId: String,
    @SerializedName("signature_type") val signatureType: String,
    @SerializedName("capture_method") val captureMethod: String = "SIGNATURE",
    @SerializedName("storage_key") val storageKey: String,
    @SerializedName("content_type") val contentType: String? = null,
    @SerializedName("file_size_bytes") val fileSizeBytes: Long? = null,
    @SerializedName("created_by") val createdBy: String? = null,
    @SerializedName("signed_at") val signedAt: String,
    @SerializedName("superseded_at") val supersededAt: String? = null,
) {
    val isEmployee: Boolean get() = signatureType == "EMPLOYEE"
    val isCustomer: Boolean get() = signatureType == "CUSTOMER"
    val isPhotoUpload: Boolean get() = captureMethod == "PHOTO_UPLOAD"
    val isSuperseded: Boolean get() = supersededAt != null
}
