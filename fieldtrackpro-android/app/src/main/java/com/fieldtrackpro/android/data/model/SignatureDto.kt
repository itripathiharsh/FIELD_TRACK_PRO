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
    @SerializedName("storage_key") val storageKey: String,
    @SerializedName("signed_at") val signedAt: String
) {
    val isEmployee: Boolean get() = signatureType == "EMPLOYEE"
    val isCustomer: Boolean get() = signatureType == "CUSTOMER"
}
