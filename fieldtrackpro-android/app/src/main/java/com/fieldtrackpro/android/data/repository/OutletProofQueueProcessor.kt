package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.OutletProofApi
import com.fieldtrackpro.android.data.local.ConflictType
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.OutletProofStore
import com.fieldtrackpro.android.data.local.PendingAction
import com.fieldtrackpro.android.data.local.SyncConflict
import com.fieldtrackpro.android.data.local.SyncErrorClass
import com.fieldtrackpro.android.data.local.SyncErrorPolicy
import com.fieldtrackpro.android.data.model.OutletProofRead
import com.fieldtrackpro.android.data.remote.ApiErrorParser
import com.fieldtrackpro.android.data.remote.OutletProofMultipart
import kotlinx.coroutines.CancellationException
import java.io.File

/** Result of replaying one queued OUTLET_PROOF action. */
sealed class OutletProofReplayOutcome {
    /** Proof is on the server; the action was removed from the queue and its photo deleted. */
    data class Synced(val proof: OutletProofRead) : OutletProofReplayOutcome()

    /** HTTP 401: pause the whole sync, queue untouched. */
    object AuthExpired : OutletProofReplayOutcome()

    /** Network/5xx/408/429: keep queued, retry later with the SAME idempotency key. */
    object Retry : OutletProofReplayOutcome()

    /** Will never succeed by retrying: caller moves it to conflicts so the user sees the server message. */
    data class Conflict(val conflict: SyncConflict) : OutletProofReplayOutcome()
}

/** Stale-capture conflicts carry this code in [SyncConflict.serverStatus]; the UI offers a RETAKE action for them. */
const val OUTLET_PROOF_STALE_STATUS = "OUTLET_PROOF_STALE_CAPTURE"

val SyncConflict.isStaleOutletProof: Boolean
    get() = pendingAction.isOutletProof && serverStatus == OUTLET_PROOF_STALE_STATUS

/** Any queued outlet proof that was rejected and can only be fixed by taking the photo again. */
val SyncConflict.needsOutletRetake: Boolean
    get() = pendingAction.isOutletProof && pendingAction.outletProofPayload?.customerId != null &&
        serverStatus != null && OutletProofMessages.requiresRetake(serverStatus, null)

/**
 * Replays a queued offline outlet proof (mirrors [PaymentQueueProcessor]). The idempotency key is the one generated
 * at the shutter click, so a lost response followed by a retry returns the stored proof (201) instead of a duplicate.
 *
 * Product caveat (reported to the owner): the server only accepts a capture <= 180 s old, so a proof that stayed
 * queued longer is rejected with 422 OUTLET_PROOF_STALE_CAPTURE. That becomes a visible conflict with a RETAKE action.
 */
class OutletProofQueueProcessor(
    private val api: OutletProofApi,
    private val queue: OfflineQueueManager,
    private val readFile: (String) -> ByteArray? = { path ->
        try { File(path).takeIf { it.isFile }?.readBytes() } catch (e: Exception) { null }
    },
    private val deleteFile: (String) -> Unit = { OutletProofStore.delete(it) }
) {

    suspend fun replay(action: PendingAction): OutletProofReplayOutcome {
        val payload = action.outletProofPayload
            ?: return OutletProofReplayOutcome.Conflict(
                SyncConflict(
                    pendingAction = action,
                    conflictType = ConflictType.SERVER_REJECTED,
                    serverStatus = null,
                    message = "Queued outlet photo data is unreadable; it was not sent. Please retake the photo."
                )
            )
        val path = payload.photoPath
        val bytes = if (path.isNullOrBlank()) null else readFile(path)
        if (bytes == null || bytes.isEmpty()) {
            return OutletProofReplayOutcome.Conflict(
                SyncConflict(
                    pendingAction = action,
                    conflictType = ConflictType.SERVER_REJECTED,
                    serverStatus = "PHOTO_MISSING",
                    message = OutletProofMessages.PHOTO_MISSING
                )
            )
        }

        val response = try {
            api.uploadOutletProof(OutletProofMultipart.build(payload, bytes))
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            return OutletProofReplayOutcome.Retry
        }

        if (response.isSuccessful) {
            // 201 (also with the existing record on a duplicate key) both mean "stored".
            val proof = response.body() ?: return OutletProofReplayOutcome.Retry
            queue.removeAction(action.id)
            path?.let(deleteFile)
            return OutletProofReplayOutcome.Synced(proof)
        }

        val code = response.code()
        val errorBodyText = if (code == 403) try { response.errorBody()?.string() } catch (e: Exception) { null } else null
        if (SyncErrorPolicy.isPasswordChangeRequired(code, errorBodyText)) return OutletProofReplayOutcome.AuthExpired
        return when {
            SyncErrorPolicy.classify(code) == SyncErrorClass.AUTH_EXPIRED -> OutletProofReplayOutcome.AuthExpired
            SyncErrorPolicy.isTransient(code) -> OutletProofReplayOutcome.Retry
            SyncErrorPolicy.classify(code) == SyncErrorClass.NOT_AVAILABLE -> {
                path?.let(deleteFile)
                OutletProofReplayOutcome.Conflict(
                    SyncConflict(
                        pendingAction = action,
                        conflictType = ConflictType.VISIT_UNAVAILABLE,
                        serverStatus = "HTTP_404",
                        message = "The outlet for this photo is no longer available or is not assigned to you. The photo was not submitted."
                    )
                )
            }
            else -> {
                val err = ApiErrorParser.parse(code, errorBodyText ?: try { response.errorBody()?.string() } catch (e: Exception) { null })
                // The photo can never be re-sent as is (stale, duplicate, rejected...): free the file now.
                path?.let(deleteFile)
                OutletProofReplayOutcome.Conflict(
                    SyncConflict(
                        pendingAction = action,
                        conflictType = ConflictType.SERVER_REJECTED,
                        serverStatus = err.code ?: code.toString(),
                        message = OutletProofMessages.forCode(err.code, code, err.message)
                    )
                )
            }
        }
    }
}
