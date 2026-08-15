package com.fieldtrackpro.android.data.api

import com.fieldtrackpro.android.data.model.AccountSummaryDto
import com.fieldtrackpro.android.data.model.InvoiceDto
import com.fieldtrackpro.android.data.model.PaymentCreateRequest
import com.fieldtrackpro.android.data.model.PaymentDto
import com.fieldtrackpro.android.data.model.PaymentProofDownloadResponse
import com.fieldtrackpro.android.data.model.PaymentProofDto
import okhttp3.MultipartBody
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path

interface CollectionApi {
    @GET("api/v1/customers/{customer_id}/account")
    suspend fun getAccountSummary(
        @Path("customer_id") customerId: String
    ): Response<AccountSummaryDto>

    @GET("api/v1/customers/{customer_id}/invoices")
    suspend fun getCustomerInvoices(
        @Path("customer_id") customerId: String
    ): Response<List<InvoiceDto>>

    @POST("api/v1/payments")
    suspend fun createPayment(
        @Body request: PaymentCreateRequest
    ): Response<PaymentDto>

    @GET("api/v1/payments/{payment_id}")
    suspend fun getPayment(
        @Path("payment_id") paymentId: String
    ): Response<PaymentDto>

    @Multipart
    @POST("api/v1/payments/{payment_id}/proof")
    suspend fun uploadPaymentProof(
        @Path("payment_id") paymentId: String,
        @Part file: MultipartBody.Part
    ): Response<PaymentProofDto>

    @GET("api/v1/payments/proofs/{proof_id}/download")
    suspend fun getProofDownloadUrl(
        @Path("proof_id") proofId: String
    ): Response<PaymentProofDownloadResponse>
}
