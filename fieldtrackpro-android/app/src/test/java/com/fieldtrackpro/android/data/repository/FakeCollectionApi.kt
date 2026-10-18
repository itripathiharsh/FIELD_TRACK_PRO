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
import okhttp3.ResponseBody.Companion.toResponseBody
import retrofit2.Response
import java.io.IOException

/**
 * Scriptable in-memory backend that mimics POST /payments idempotency: a repeated (visit, idempotency_key)
 * returns the existing record, and proof re-uploads are not duplicated.
 */
class FakeCollectionApi : CollectionApi {
    var createBehavior: () -> Response<PaymentDto>? = { null } // null => default behaviour (dedup store)
    var createThrows: IOException? = null
    var proofBehavior: () -> Response<PaymentProofDto>? = { null }
    var proofThrows: IOException? = null

    val createCalls = mutableListOf<PaymentCreateRequest>()
    var proofUploadCalls = 0
    val storedPayments = mutableMapOf<String, PaymentDto>() // key = visit|idempotency
    val log = mutableListOf<String>()

    fun err(code: Int, body: String = "{}") =
        Response.error<PaymentDto>(code, body.toResponseBody("application/json".toMediaTypeOrNull()))

    fun proofErr(code: Int, body: String = "{}") =
        Response.error<PaymentProofDto>(code, body.toResponseBody("application/json".toMediaTypeOrNull()))

    override suspend fun createPayment(request: PaymentCreateRequest): Response<PaymentDto> {
        log += "createPayment:${request.visitId}"
        createCalls += request
        createThrows?.let { throw it }
        createBehavior()?.let { return it }
        val k = "${request.visitId}|${request.idempotencyKey}"
        val dto = storedPayments.getOrPut(k) {
            PaymentDto(
                id = "pay-${storedPayments.size + 1}", visitId = request.visitId, customerId = "c1", employeeId = "e1",
                amount = request.amount, paymentMethod = request.paymentMethod, paymentDate = request.paymentDate,
                status = "PENDING_VERIFICATION", createdAt = "2026-01-01T00:00:00Z"
            )
        }
        return Response.success(201, dto)
    }

    override suspend fun uploadPaymentProof(paymentId: String, file: MultipartBody.Part): Response<PaymentProofDto> {
        log += "uploadProof:$paymentId"
        proofUploadCalls++
        proofThrows?.let { throw it }
        proofBehavior()?.let { return it }
        return Response.success(
            201,
            PaymentProofDto(id = "proof-$proofUploadCalls", paymentId = paymentId, storageKey = "k", fileSizeBytes = 3, uploadedAt = "t")
        )
    }

    override suspend fun getAccountSummary(customerId: String): Response<AccountSummaryDto> = throw UnsupportedOperationException()
    override suspend fun getCustomerInvoices(customerId: String): Response<List<InvoiceDto>> = throw UnsupportedOperationException()
    override suspend fun getPayment(paymentId: String): Response<PaymentDto> = throw UnsupportedOperationException()
    override suspend fun getProofDownloadUrl(proofId: String): Response<PaymentProofDownloadResponse> = throw UnsupportedOperationException()
}
