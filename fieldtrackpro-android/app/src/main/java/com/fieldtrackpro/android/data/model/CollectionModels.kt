package com.fieldtrackpro.android.data.model

import com.google.gson.annotations.SerializedName

/**
 * P1: Collections / Invoices / Payments (Outlet Account).
 *
 * Aligned field-for-field with the backend's InvoiceRead / PaymentRead /
 * AccountSummary schemas. Aging fields are always computed server-side
 * (app.services.aging_service) - never recalculated here.
 */

data class InvoiceDto(
    val id: String,
    @SerializedName("customer_id") val customerId: String,
    @SerializedName("invoice_number") val invoiceNumber: String,
    @SerializedName("invoice_date") val invoiceDate: String,
    @SerializedName("due_date") val dueDate: String? = null,
    val amount: String,
    val brand: String? = null,
    val source: String,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("verified_paid_amount") val verifiedPaidAmount: String,
    @SerializedName("remaining_amount") val remainingAmount: String,
    @SerializedName("days_outstanding") val daysOutstanding: Int,
    @SerializedName("payment_status") val paymentStatus: String,
    @SerializedName("aging_status") val agingStatus: String,
    @SerializedName("mis_bucket") val misBucket: String,
)

data class PaymentProofDto(
    val id: String,
    @SerializedName("payment_id") val paymentId: String,
    @SerializedName("storage_key") val storageKey: String,
    @SerializedName("file_size_bytes") val fileSizeBytes: Long,
    @SerializedName("original_filename") val originalFilename: String? = null,
    @SerializedName("uploaded_at") val uploadedAt: String,
)

data class PaymentDto(
    val id: String,
    @SerializedName("visit_id") val visitId: String,
    @SerializedName("customer_id") val customerId: String,
    @SerializedName("employee_id") val employeeId: String,
    @SerializedName("invoice_id") val invoiceId: String? = null,
    val amount: String,
    @SerializedName("payment_method") val paymentMethod: String,
    @SerializedName("payment_date") val paymentDate: String,
    @SerializedName("cheque_number") val chequeNumber: String? = null,
    @SerializedName("cheque_bank_name") val chequeBankName: String? = null,
    @SerializedName("utr_reference") val utrReference: String? = null,
    val notes: String? = null,
    val status: String,
    @SerializedName("rejection_reason") val rejectionReason: String? = null,
    @SerializedName("created_at") val createdAt: String,
    val proofs: List<PaymentProofDto> = emptyList(),
)

data class BrandSummaryDto(
    val brand: String,
    @SerializedName("total_invoiced") val totalInvoiced: String,
    @SerializedName("total_paid") val totalPaid: String,
    @SerializedName("total_outstanding") val totalOutstanding: String,
    // P2-A: brand-wise history enrichment - mirrors app/schemas/account.py's
    // BrandSummary exactly.
    @SerializedName("overdue_amount") val overdueAmount: String = "0",
    @SerializedName("invoice_count") val invoiceCount: Int = 0,
    @SerializedName("payment_count") val paymentCount: Int = 0,
    @SerializedName("latest_invoice_date") val latestInvoiceDate: String? = null,
    @SerializedName("latest_payment_date") val latestPaymentDate: String? = null,
)

data class AccountSummaryDto(
    @SerializedName("customer_id") val customerId: String,
    @SerializedName("customer_name") val customerName: String,
    @SerializedName("outlet_code") val outletCode: String? = null,
    @SerializedName("total_invoiced") val totalInvoiced: String,
    @SerializedName("total_paid") val totalPaid: String,
    @SerializedName("total_outstanding") val totalOutstanding: String,
    @SerializedName("overdue_amount") val overdueAmount: String,
    @SerializedName("max_days_outstanding") val maxDaysOutstanding: Int,
    @SerializedName("collection_status") val collectionStatus: String,
    @SerializedName("most_recent_payment") val mostRecentPayment: PaymentDto? = null,
    @SerializedName("recent_invoices") val recentInvoices: List<InvoiceDto> = emptyList(),
    @SerializedName("recent_payments") val recentPayments: List<PaymentDto> = emptyList(),
    @SerializedName("brand_summary") val brandSummary: List<BrandSummaryDto> = emptyList(),
)

data class PaymentCreateRequest(
    @SerializedName("visit_id") val visitId: String,
    @SerializedName("invoice_id") val invoiceId: String? = null,
    val amount: String,
    @SerializedName("payment_method") val paymentMethod: String,
    @SerializedName("payment_date") val paymentDate: String,
    @SerializedName("cheque_number") val chequeNumber: String? = null,
    @SerializedName("cheque_bank_name") val chequeBankName: String? = null,
    @SerializedName("utr_reference") val utrReference: String? = null,
    val notes: String? = null,
)

data class PaymentProofDownloadResponse(
    @SerializedName("download_url") val downloadUrl: String,
    @SerializedName("expires_in_minutes") val expiresInMinutes: Int,
)
