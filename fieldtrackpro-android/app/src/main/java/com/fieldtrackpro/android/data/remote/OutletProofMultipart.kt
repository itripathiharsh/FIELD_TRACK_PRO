package com.fieldtrackpro.android.data.remote

import com.fieldtrackpro.android.data.local.OutletProofPayload
import com.fieldtrackpro.android.data.model.OutletProofFields
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.Locale

/** Builds the multipart body of POST /customers/outlet-proofs (photo + GPS fix are ONE bundle). */
object OutletProofMultipart {
    private const val FILE_NAME = "outlet_proof.jpg"

    fun build(payload: OutletProofPayload, jpegBytes: ByteArray): List<MultipartBody.Part> {
        val parts = mutableListOf<MultipartBody.Part>()
        parts += MultipartBody.Part.createFormData(
            OutletProofFields.PHOTO, FILE_NAME, jpegBytes.toRequestBody("image/jpeg".toMediaType())
        )
        payload.latitude?.let { parts += text(OutletProofFields.LATITUDE, fmt(it, 7)) }
        payload.longitude?.let { parts += text(OutletProofFields.LONGITUDE, fmt(it, 7)) }
        payload.accuracyM?.let { parts += text(OutletProofFields.ACCURACY_M, fmt(it, 2)) }
        payload.capturedAt?.let { parts += text(OutletProofFields.CAPTURED_AT, it) }
        parts += text(OutletProofFields.IS_MOCK_LOCATION, if (payload.isMock) "true" else "false")
        payload.idempotencyKey?.let { parts += text(OutletProofFields.IDEMPOTENCY_KEY, it) }
        payload.deviceInfo?.takeIf { it.isNotBlank() }?.let { parts += text(OutletProofFields.DEVICE_INFO, it.take(200)) }
        // OMITTED for a new outlet: the proof is then stored UNATTACHED for 48 h.
        payload.customerId?.takeIf { it.isNotBlank() }?.let { parts += text(OutletProofFields.CUSTOMER_ID, it) }
        return parts
    }

    private fun text(name: String, value: String) = MultipartBody.Part.createFormData(name, value)

    private fun fmt(v: Double, decimals: Int) = String.format(Locale.US, "%.${decimals}f", v)
}
