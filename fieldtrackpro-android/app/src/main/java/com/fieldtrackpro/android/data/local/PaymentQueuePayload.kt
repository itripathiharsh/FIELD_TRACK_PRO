package com.fieldtrackpro.android.data.local

import com.fieldtrackpro.android.data.model.BrandAllocationInput
import com.fieldtrackpro.android.data.model.PaymentCreateRequest
import com.google.gson.annotations.SerializedName

/**
 * Everything needed to replay a payment collection that was captured offline (PendingAction.paymentPayload).
 * All fields are nullable/defaulted so persisted JSON stays readable across app versions.
 *
 * [idempotencyKey] is generated ONCE when the form is submitted and reused on every retry; the backend dedups on
 * (visit, idempotency_key), so a retry can never create a second payment.
 */
data class PaymentQueuePayload(
    @SerializedName("idempotencyKey") val idempotencyKey: String? = null,
    @SerializedName("customerId") val customerId: String? = null,
    @SerializedName("outletName") val outletName: String? = null,
    @SerializedName("invoiceId") val invoiceId: String? = null,
    @SerializedName("amount") val amount: String? = null,
    @SerializedName("paymentMethod") val paymentMethod: String? = null,
    @SerializedName("paymentDate") val paymentDate: String? = null,
    @SerializedName("chequeNumber") val chequeNumber: String? = null,
    @SerializedName("chequeBankName") val chequeBankName: String? = null,
    @SerializedName("utrReference") val utrReference: String? = null,
    @SerializedName("notes") val notes: String? = null,
    @SerializedName("allocations") val allocations: List<BrandAllocationInput>? = null,
    /** Absolute paths of proof photos copied into app-private storage; removed as each upload succeeds. */
    @SerializedName("proofPaths") val proofPaths: List<String>? = null,
    /** Set once the server confirmed the payment, so a retry only has to finish the proof uploads. */
    @SerializedName("serverPaymentId") val serverPaymentId: String? = null
) {
    fun toRequest(visitId: String): PaymentCreateRequest = PaymentCreateRequest(
        visitId = visitId,
        invoiceId = invoiceId,
        amount = amount.orEmpty(),
        paymentMethod = paymentMethod.orEmpty(),
        paymentDate = paymentDate.orEmpty(),
        chequeNumber = chequeNumber,
        chequeBankName = chequeBankName,
        utrReference = utrReference,
        notes = notes,
        idempotencyKey = idempotencyKey,
        allocations = allocations
    )
}
