package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.SignatureApi
import com.fieldtrackpro.android.data.model.SignatureDto
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody

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
        signatureImageBase64: String
    ): Resource<SignatureDto> {
        return try {
            val typeBody = signatureType.toRequestBody("text/plain".toMediaTypeOrNull())
            val typePart = MultipartBody.Part.createFormData("signature_type", null, typeBody)

            val imageBody = signatureImageBase64.toRequestBody("text/plain".toMediaTypeOrNull())
            val imagePart = MultipartBody.Part.createFormData("signature_image_base64", null, imageBody)

            val response = signatureApi.uploadSignature(visitId, typePart, imagePart)
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
}
