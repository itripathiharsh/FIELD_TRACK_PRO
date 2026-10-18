package com.fieldtrackpro.android.data.model

import com.google.gson.annotations.SerializedName

/**
 * Response of POST /customers/outlet-proofs (OutletProofRead). Only the fields the app uses are mapped;
 * everything is defaulted/nullable so a server-side additive change never breaks parsing.
 *
 * kind:   INITIAL | CONFIRMATION | CHANGE_REQUEST
 * status: UNATTACHED | PENDING | CONFIRMED | APPROVED | REJECTED | SUPERSEDED
 */
data class OutletProofRead(
    val id: String,
    @SerializedName("customer_id") val customerId: String? = null,
    @SerializedName("prospect_id") val prospectId: String? = null,
    val kind: String? = null,
    val status: String? = null,
    @SerializedName("is_primary") val isPrimary: Boolean = false,
    val latitude: Double? = null,
    val longitude: Double? = null,
    @SerializedName("accuracy_m") val accuracyM: Double? = null,
    @SerializedName("captured_at") val capturedAt: String? = null,
    @SerializedName("distance_from_verified_m") val distanceFromVerifiedM: Double? = null,
    @SerializedName("image_url") val imageUrl: String? = null,
    @SerializedName("rejection_reason") val rejectionReason: String? = null
)

/** Multipart field names of POST /customers/outlet-proofs (single source of truth, unit-tested). */
object OutletProofFields {
    const val PHOTO = "photo"
    const val LATITUDE = "latitude"
    const val LONGITUDE = "longitude"
    const val ACCURACY_M = "accuracy_m"
    const val CAPTURED_AT = "captured_at"
    const val IS_MOCK_LOCATION = "is_mock_location"
    const val IDEMPOTENCY_KEY = "idempotency_key"
    const val DEVICE_INFO = "device_info"
    const val CUSTOMER_ID = "customer_id"
}
