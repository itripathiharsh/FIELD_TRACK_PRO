package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.CollectionApi
import com.fieldtrackpro.android.data.local.ConflictType
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.PaymentProofStore
import com.fieldtrackpro.android.data.local.PendingAction
import com.fieldtrackpro.android.data.local.SyncConflict
import com.fieldtrackpro.android.data.local.SyncErrorClass
import com.fieldtrackpro.android.data.local.SyncErrorPolicy
import com.fieldtrackpro.android.data.remote.ApiErrorParser
import kotlinx.coroutines.CancellationException
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import retrofit2.Response
import java.io.File

/** Result of replaying one queued PAYMENT_CREATE action. */
sealed class PaymentReplayOutcome {
    /** Payment (and every proof) is on the server; the action was removed from the queue. */
    object Synced : PaymentReplayOutcome()

    /** HTTP 401: pause the whole sync, queue untouched. */
    object AuthExpired : PaymentReplayOutcome()

    /** Network/5xx/408/429: keep queued, retry later with the SAME idempotency key. */
    object Retry : PaymentReplayOutcome()

    /** Will never succeed by retrying: caller moves it to conflicts so the user sees the server message. */
    data class Conflict(val conflict: SyncConflict) : PaymentReplayOutcome()
}

/**
 * Replays a queued offline payment: create (same idempotency key => backend returns the existing record on a
 * duplicate), then upload each queued proof (backend dedups by checksum), then remove from the queue.
 * Progress (server payment id, proofs still to upload) is persisted after each step so a crash/retry never
 * creates a second payment or loses a proof.
 */
class PaymentQueueProcessor(
    private val collectionApi: CollectionApi,
    private val queue: OfflineQueueManager,
    private val readFile: (String) -> ByteArray? = { path ->
        try { File(path).takeIf { it.isFile }?.readBytes() } catch (e: Exception) { null }
    },
    private val deleteFile: (String) -> Unit = { PaymentProofStore.delete(it) }
) {

    suspend fun replay(action: PendingAction): PaymentReplayOutcome {
        var payload = action.paymentPayload
            ?: return PaymentReplayOutcome.Conflict(
                SyncConflict(
                    pendingAction = action,
                    conflictType = ConflictType.SERVER_REJECTED,
                    serverStatus = null,
                    message = "Queued payment data is unreadable; it was not sent. Please record the payment again."
                )
            )
        var current = action

        if (payload.serverPaymentId.isNullOrBlank()) {
            val response = try {
                collectionApi.createPayment(payload.toRequest(action.visitId))
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                return PaymentReplayOutcome.Retry
            }
            if (response.isSuccessful) {
                // 200/201 (201 with the existing record on a duplicate key) both mean "recorded".
                val id = response.body()?.id ?: return PaymentReplayOutcome.Retry
                payload = payload.copy(serverPaymentId = id)
                current = action.copy(paymentPayload = payload)
                queue.updateAction(current)
            } else {
                return failureOutcome(current, response)
            }
        }

        val paymentId = payload.serverPaymentId!!
        val problems = mutableListOf<String>()
        var remaining = payload.proofPaths.orEmpty()
        var keptPaths = emptyList<String>()
        for (path in payload.proofPaths.orEmpty()) {
            val bytes = readFile(path)
            if (bytes == null || bytes.isEmpty()) {
                problems += "a proof photo file was missing on the device"
            } else {
                val part = MultipartBody.Part.createFormData(
                    "file", "proof_${paymentId.take(8)}_${remaining.size}.jpg",
                    bytes.toRequestBody("image/jpeg".toMediaTypeOrNull())
                )
                val response = try {
                    collectionApi.uploadPaymentProof(paymentId, part)
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    return PaymentReplayOutcome.Retry
                }
                if (!response.isSuccessful) {
                    val code = response.code()
                    if (code == 401) return PaymentReplayOutcome.AuthExpired
                    val body = errorBodyOnce(response)
                    if (SyncErrorPolicy.isPasswordChangeRequired(code, body)) return PaymentReplayOutcome.AuthExpired
                    if (SyncErrorPolicy.isTransient(code)) return PaymentReplayOutcome.Retry
                    problems += "proof rejected (HTTP $code): ${messageFrom(code, body)}"
                    if (isTooLargeRejection(code, body)) {
                        // Too large / unprocessable image: do NOT delete the only copy. It stays on the device,
                        // referenced by the conflict, until the user retakes the photo or discards the item.
                        keptPaths = keptPaths + path
                        remaining = remaining - path
                        payload = payload.copy(proofPaths = remaining)
                        current = current.copy(paymentPayload = payload)
                        queue.updateAction(current)
                        continue
                    }
                }
            }
            // Resolved (uploaded or permanently unusable): never upload it again.
            remaining = remaining - path
            payload = payload.copy(proofPaths = remaining)
            current = current.copy(paymentPayload = payload)
            queue.updateAction(current)
            deleteFile(path)
        }

        queue.removeAction(current.id)
        if (keptPaths.isNotEmpty()) {
            // The conflict's action keeps pointing at the preserved file(s) so they stay referenced (not pruned)
            // and the user has a retake/discard choice.
            current = current.copy(paymentPayload = payload.copy(proofPaths = keptPaths))
        }
        if (problems.isNotEmpty()) {
            return PaymentReplayOutcome.Conflict(
                SyncConflict(
                    pendingAction = current,
                    conflictType = ConflictType.SERVER_REJECTED,
                    serverStatus = null,
                    message = "Payment was recorded, but ${problems.size} proof photo(s) could not be attached: " +
                        problems.joinToString("; ")
                )
            )
        }
        return PaymentReplayOutcome.Synced
    }

    private fun failureOutcome(action: PendingAction, response: Response<*>): PaymentReplayOutcome {
        val code = response.code()
        val body = errorBodyOnce(response)
        if (SyncErrorPolicy.isPasswordChangeRequired(code, body)) return PaymentReplayOutcome.AuthExpired
        return when {
            SyncErrorPolicy.classify(code) == SyncErrorClass.AUTH_EXPIRED -> PaymentReplayOutcome.AuthExpired
            SyncErrorPolicy.classify(code) == SyncErrorClass.NOT_AVAILABLE ->
                PaymentReplayOutcome.Conflict(SyncErrorPolicy.paymentNotAvailableConflict(action))
            SyncErrorPolicy.isTransient(code) -> PaymentReplayOutcome.Retry
            else -> PaymentReplayOutcome.Conflict(
                SyncErrorPolicy.paymentRejectedConflict(action, code, messageFrom(code, body))
            )
        }
    }

    private fun errorBodyOnce(response: Response<*>): String? =
        try { response.errorBody()?.string() } catch (e: Exception) { null }

    private fun messageFrom(code: Int, body: String?): String = ApiErrorParser.parse(code, body).message

    companion object {
        /** HTTP 413, or 422 whose message says the image is too large / too big (backend caps images at 10 MB). */
        fun isTooLargeRejection(code: Int, body: String?): Boolean {
            if (code == 413) return true
            if (code != 422) return false
            val text = (ApiErrorParser.parse(code, body).let { it.code.orEmpty() + " " + it.message } + " " + body.orEmpty())
                .lowercase()
            return text.contains("too large") || text.contains("too big") || text.contains("exceeds") ||
                text.contains("file_too_large") || text.contains("max size") || text.contains("10 mb")
        }
    }
}
