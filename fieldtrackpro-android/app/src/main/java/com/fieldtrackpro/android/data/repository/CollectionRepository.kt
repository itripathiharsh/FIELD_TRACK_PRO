package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.CollectionApi
import com.fieldtrackpro.android.data.model.AccountSummaryDto
import com.fieldtrackpro.android.data.model.InvoiceDto
import com.fieldtrackpro.android.data.model.PaymentCreateRequest
import com.fieldtrackpro.android.data.model.PaymentDto
import com.fieldtrackpro.android.data.model.PaymentProofDownloadResponse
import com.fieldtrackpro.android.data.model.PaymentProofDto
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody

class CollectionRepository(private val collectionApi: CollectionApi) {

    suspend fun getAccountSummary(customerId: String): Resource<AccountSummaryDto> {
        return try {
            val response = collectionApi.getAccountSummary(customerId)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Failed to load outlet account (${response.code()})", response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    suspend fun getCustomerInvoices(customerId: String): Resource<List<InvoiceDto>> {
        return try {
            val response = collectionApi.getCustomerInvoices(customerId)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Failed to load invoice history (${response.code()})", response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    suspend fun createPayment(request: PaymentCreateRequest): Resource<PaymentDto> {
        return try {
            val response = collectionApi.createPayment(request)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                val err = response.errorBody()?.string() ?: "Collection rejected"
                Resource.Error("Failed to record collection (${response.code()}): $err", response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    suspend fun uploadPaymentProof(
        paymentId: String,
        fileName: String,
        mimeType: String,
        fileBytes: ByteArray
    ): Resource<PaymentProofDto> {
        return try {
            val reqBody = fileBytes.toRequestBody(mimeType.toMediaTypeOrNull())
            val part = MultipartBody.Part.createFormData("file", fileName, reqBody)
            val response = collectionApi.uploadPaymentProof(paymentId, part)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                val err = response.errorBody()?.string() ?: "Upload rejected"
                Resource.Error("Proof upload failed (${response.code()}): $err")
            }
        } catch (e: Exception) {
            Resource.Error("Upload failed: ${e.localizedMessage}")
        }
    }

    suspend fun getProofDownloadUrl(proofId: String): Resource<PaymentProofDownloadResponse> {
        return try {
            val response = collectionApi.getProofDownloadUrl(proofId)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Failed to get proof URL (${response.code()})")
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }
}
