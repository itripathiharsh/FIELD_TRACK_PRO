package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.PaymentProofStore
import com.fieldtrackpro.android.data.local.PaymentQueuePayload
import com.fieldtrackpro.android.data.local.PendingAction
import com.fieldtrackpro.android.data.local.SyncErrorPolicy
import com.fieldtrackpro.android.data.model.BrandAllocationInput
import com.fieldtrackpro.android.data.model.PaymentCreateRequest
import com.fieldtrackpro.android.data.model.PaymentDto
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/** What the collection form must show after a submit. */
sealed class PaymentSubmitOutcome {
    /** Recorded on the server (every proof uploaded). */
    data class Created(val payment: PaymentDto) : PaymentSubmitOutcome()

    /** Recorded on the server, but some proofs could not be uploaded: they were queued and will sync automatically. */
    data class CreatedProofsQueued(val payment: PaymentDto, val queuedProofs: Int) : PaymentSubmitOutcome()

    /** No connectivity/timeout/5xx: saved on the device, will sync automatically. NOT an error. */
    data class SavedOffline(val action: PendingAction) : PaymentSubmitOutcome()

    /** Definitive rejection (validation, auth, 404...): show the message so the user can fix it. */
    data class Rejected(val message: String, val code: Int?) : PaymentSubmitOutcome()
}

/**
 * Online-first payment submission with an offline fallback. The idempotency key is supplied by the caller and is
 * generated once per form submission, so a queued retry or a re-tap can never create a second payment.
 */
class PaymentSubmitter(
    private val repository: CollectionRepository,
    private val queue: OfflineQueueManager?,
    private val readFile: (String) -> ByteArray? = { path ->
        try { File(path).takeIf { it.isFile }?.readBytes() } catch (e: Exception) { null }
    },
    private val deleteFile: (String) -> Unit = { PaymentProofStore.delete(it) }
) {

    suspend fun submit(
        userId: String?,
        visitId: String,
        customerId: String?,
        outletName: String?,
        idempotencyKey: String,
        invoiceId: String?,
        amount: String,
        paymentMethod: String,
        paymentDate: String,
        chequeNumber: String?,
        chequeBankName: String?,
        utrReference: String?,
        notes: String?,
        allocations: List<BrandAllocationInput>?,
        proofPaths: List<String>
    ): PaymentSubmitOutcome {
        val request = PaymentCreateRequest(
            visitId = visitId, invoiceId = invoiceId, amount = amount, paymentMethod = paymentMethod,
            paymentDate = paymentDate, chequeNumber = chequeNumber, chequeBankName = chequeBankName,
            utrReference = utrReference, notes = notes, idempotencyKey = idempotencyKey, allocations = allocations
        )
        val basePayload = PaymentQueuePayload(
            idempotencyKey = idempotencyKey, customerId = customerId, outletName = outletName, invoiceId = invoiceId,
            amount = amount, paymentMethod = paymentMethod, paymentDate = paymentDate, chequeNumber = chequeNumber,
            chequeBankName = chequeBankName, utrReference = utrReference, notes = notes, allocations = allocations,
            proofPaths = proofPaths
        )

        return when (val res = repository.createPayment(request)) {
            is Resource.Success -> {
                val payment = res.data
                val failed = mutableListOf<String>()
                for (path in proofPaths) {
                    val bytes = readFile(path)
                    if (bytes == null || bytes.isEmpty()) continue // unreadable file: nothing to retry
                    when (repository.uploadPaymentProof(payment.id, "proof_${payment.id.take(8)}.jpg", "image/jpeg", bytes)) {
                        is Resource.Success -> deleteFile(path)
                        else -> failed += path
                    }
                }
                if (failed.isEmpty()) {
                    PaymentSubmitOutcome.Created(payment)
                } else {
                    val queued = withContext(Dispatchers.IO) { enqueue(userId, visitId, basePayload.copy(serverPaymentId = payment.id, proofPaths = failed)) }
                    if (queued != null) PaymentSubmitOutcome.CreatedProofsQueued(payment, failed.size)
                    else PaymentSubmitOutcome.Created(payment)
                }
            }
            is Resource.Error -> {
                // 403 PASSWORD_CHANGE_REQUIRED (forced password change): do not lose the payment - keep it on the
                // device (SavedOffline); it syncs automatically once the new password is set.
                val passwordChangePending = res.code == 403 && res.message.contains("PASSWORD_CHANGE_REQUIRED")
                if (SyncErrorPolicy.isTransient(res.code) || passwordChangePending) {
                    val queued = withContext(Dispatchers.IO) { enqueue(userId, visitId, basePayload) } // durable commit() off the main thread
                    if (queued != null) PaymentSubmitOutcome.SavedOffline(queued)
                    else PaymentSubmitOutcome.Rejected("Could not save the payment offline. ${res.message}", res.code)
                } else {
                    PaymentSubmitOutcome.Rejected(res.message, res.code)
                }
            }
            else -> PaymentSubmitOutcome.Rejected("Unexpected state", null)
        }
    }

    private fun enqueue(userId: String?, visitId: String, payload: PaymentQueuePayload): PendingAction? {
        val manager = queue ?: return null
        if (userId.isNullOrBlank()) return null
        val action = PendingAction(
            userId = userId,
            visitId = visitId,
            actionType = PendingAction.TYPE_PAYMENT_CREATE,
            latitude = 0.0,
            longitude = 0.0,
            paymentPayload = payload
        )
        manager.enqueueAction(action)
        return action
    }
}
