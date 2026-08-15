package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.MediaApi
import com.fieldtrackpro.android.data.api.MediaDownloadResponse
import com.fieldtrackpro.android.data.model.MediaDto
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody

class MediaRepository(private val mediaApi: MediaApi) {
    suspend fun getVisitMedia(visitId: String): Resource<List<MediaDto>> {
        return try {
            val response = mediaApi.getVisitMediaList(visitId)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Failed to load visit attachments (${response.code()})")
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    suspend fun getMediaMetadata(mediaId: String): Resource<MediaDto> {
        return try {
            val response = mediaApi.getMediaMetadata(mediaId)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Media not found (${response.code()})")
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    suspend fun getMediaDownloadUrl(mediaId: String): Resource<MediaDownloadResponse> {
        return try {
            val response = mediaApi.getMediaDownloadUrl(mediaId)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Failed to get download URL (${response.code()})")
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    suspend fun uploadVisitMedia(
        visitId: String,
        fileName: String,
        mimeType: String,
        fileBytes: ByteArray
    ): Resource<MediaDto> {
        return try {
            val reqBody = fileBytes.toRequestBody(mimeType.toMediaTypeOrNull())
            val part = MultipartBody.Part.createFormData("file", fileName, reqBody)
            val response = mediaApi.uploadVisitMedia(visitId, part)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                val err = response.errorBody()?.string() ?: "Upload rejected"
                Resource.Error("Media upload failed (${response.code()}): $err")
            }
        } catch (e: Exception) {
            Resource.Error("Upload failed: ${e.localizedMessage}")
        }
    }

    /** P2-B: order capture - a photographed order diary note, tied to this visit/outlet. */
    suspend fun uploadOrderCapture(
        visitId: String,
        fileName: String,
        mimeType: String,
        fileBytes: ByteArray,
        note: String?
    ): Resource<MediaDto> {
        return try {
            val reqBody = fileBytes.toRequestBody(mimeType.toMediaTypeOrNull())
            val part = MultipartBody.Part.createFormData("file", fileName, reqBody)
            val response = mediaApi.uploadVisitMedia(visitId, part, isOrder = true, note = note)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                val err = response.errorBody()?.string() ?: "Upload rejected"
                Resource.Error("Order capture failed (${response.code()}): $err")
            }
        } catch (e: Exception) {
            Resource.Error("Order capture failed: ${e.localizedMessage}")
        }
    }
}
