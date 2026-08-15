package com.fieldtrackpro.android.data.model

import com.google.gson.annotations.SerializedName

/**
 * Request body for uploading a signature/acknowledgement.
 * Matches the backend's SignatureCreate schema.
 */
data class SignatureCreateRequest(
    @SerializedName("signature_type") val signatureType: String,
    @SerializedName("signature_image_base64") val signatureImageBase64: String,
    // "SIGNATURE" (drawn on-screen) or "PHOTO_UPLOAD" (photo of an
    // already-signed document) - defaults to SIGNATURE to match the
    // pre-existing canvas-only behaviour.
    @SerializedName("capture_method") val captureMethod: String = "SIGNATURE",
)

/** Request body for POST /visits/{visit_id}/signatures/{signature_id}/replace. */
data class SignatureReplaceRequest(
    @SerializedName("signature_image_base64") val signatureImageBase64: String,
    @SerializedName("capture_method") val captureMethod: String = "SIGNATURE",
)
