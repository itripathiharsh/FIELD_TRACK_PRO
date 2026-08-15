package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.SignatureApi
import com.fieldtrackpro.android.data.model.SignatureCreateRequest
import com.fieldtrackpro.android.data.model.SignatureDto
import com.fieldtrackpro.android.data.model.SignatureReplaceRequest

class SignatureRepository(private val signatureApi: SignatureApi) {
    suspend fun getVisitSignatures(visitId: String): Resource<List<SignatureDto>> {
        return try {
            val response = signatureApi.getVisitSignatures(visitId)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Failed to load signatures (${response.code()})")
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    suspend fun uploadSignature(
        visitId: String,
        signatureType: String,
        signatureImageBase64: String,
        captureMethod: String = "SIGNATURE",
    ): Resource<SignatureDto> {
        return try {
            val payload = SignatureCreateRequest(
                signatureType = signatureType,
                signatureImageBase64 = signatureImageBase64,
                captureMethod = captureMethod,
            )
            val response = signatureApi.uploadSignature(visitId, payload)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                val err = response.errorBody()?.string() ?: "Upload rejected"
                Resource.Error("Signature upload failed (${response.code()}): $err")
            }
        } catch (e: Exception) {
            Resource.Error("Upload failed: ${e.localizedMessage}")
        }
    }

    /**
     * Correct an incorrectly-captured signature/acknowledgement. The prior
     * capture is preserved server-side (marked superseded, not deleted) -
     * this call creates a brand-new current signature, it does not edit the
     * old row in place.
     */
    suspend fun replaceSignature(
        visitId: String,
        signatureId: String,
        signatureImageBase64: String,
        captureMethod: String = "SIGNATURE",
    ): Resource<SignatureDto> {
        return try {
            val payload = SignatureReplaceRequest(
                signatureImageBase64 = signatureImageBase64,
                captureMethod = captureMethod,
            )
            val response = signatureApi.replaceSignature(visitId, signatureId, payload)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                val err = response.errorBody()?.string() ?: "Replace rejected"
                Resource.Error("Signature replace failed (${response.code()}): $err")
            }
        } catch (e: Exception) {
            Resource.Error("Replace failed: ${e.localizedMessage}")
        }
    }
}
