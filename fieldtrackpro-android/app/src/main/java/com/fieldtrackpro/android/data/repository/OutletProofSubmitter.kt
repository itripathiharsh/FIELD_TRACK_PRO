package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.OutletProofApi
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.OutletProofPayload
import com.fieldtrackpro.android.data.local.OutletProofStore
import com.fieldtrackpro.android.data.local.PendingAction
import com.fieldtrackpro.android.data.local.SyncErrorPolicy
import com.fieldtrackpro.android.data.model.OutletProofRead
import com.fieldtrackpro.android.data.remote.ApiErrorParser
import com.fieldtrackpro.android.data.remote.HttpErrors
import com.fieldtrackpro.android.data.remote.OutletProofMultipart
import com.fieldtrackpro.android.utils.OutletProofRules
import kotlinx.coroutines.CancellationException
import java.io.File
import java.util.Locale

/** What the capture/submit UI must show after an outlet-proof upload attempt. */
sealed class OutletProofOutcome {
    /** Stored on the server. */
    data class Uploaded(val proof: OutletProofRead) : OutletProofOutcome()

    /** Existing outlet, no connectivity/5xx/408/429: saved on the device, will upload when connectivity returns. */
    data class SavedOffline(val action: PendingAction) : OutletProofOutcome()

    /** NEW outlet and no connectivity: a new outlet is never queued; keep the capture and let the user retry. */
    data class NeedsInternet(val message: String = OutletProofMessages.NEW_OUTLET_NEEDS_INTERNET) : OutletProofOutcome()

    /** Definitive rejection. [retakeRequired] = only a new photo can fix it. */
    data class Rejected(
        val message: String,
        val httpStatus: Int?,
        val errorCode: String?,
        val retakeRequired: Boolean
    ) : OutletProofOutcome()
}

/**
 * Online-first outlet-proof upload with an offline fallback for EXISTING outlets (mirrors [PaymentSubmitter]).
 * The idempotency key lives in [OutletProofPayload] and is generated once at the shutter click, so a queued or
 * re-tried upload can never store a second proof.
 *
 * Design decision (new outlets): a NEW outlet is NOT queued. Its proof upload and the prospect submission must
 * happen online back-to-back (the proof id feeds the prospect request), so offline we answer
 * [OutletProofOutcome.NeedsInternet]. Only existing-outlet proofs are queued.
 */
class OutletProofSubmitter(
    private val api: OutletProofApi,
    private val queue: OfflineQueueManager?,
    private val readFile: (String) -> ByteArray? = { path ->
        try { File(path).takeIf { it.isFile }?.readBytes() } catch (e: Exception) { null }
    },
    private val deleteFile: (String) -> Unit = { OutletProofStore.delete(it) }
) {

    suspend fun submit(userId: String?, payload: OutletProofPayload): OutletProofOutcome {
        val path = payload.photoPath
        val bytes = if (path.isNullOrBlank()) null else readFile(path)
        if (bytes == null || bytes.isEmpty()) {
            return OutletProofOutcome.Rejected(OutletProofMessages.PHOTO_MISSING, null, "PHOTO_MISSING", retakeRequired = true)
        }
        if (bytes.size > OutletProofRules.MAX_PHOTO_BYTES) {
            return OutletProofOutcome.Rejected(
                OutletProofMessages.forCode("OUTLET_PROOF_IMAGE_TOO_LARGE", 413, null), 413, "OUTLET_PROOF_IMAGE_TOO_LARGE", true
            )
        }

        val response = try {
            api.uploadOutletProof(OutletProofMultipart.build(payload, bytes))
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            return transientFailure(userId, payload)
        }

        if (response.isSuccessful) {
            val proof = response.body() ?: return transientFailure(userId, payload)
            return OutletProofOutcome.Uploaded(proof)
        }
        val code = response.code()
        if (SyncErrorPolicy.isTransient(code)) return transientFailure(userId, payload)

        val err = ApiErrorParser.parse(code, try { response.errorBody()?.string() } catch (e: Exception) { null })
        return OutletProofOutcome.Rejected(
            message = OutletProofMessages.forCode(err.code, code, err.message),
            httpStatus = code,
            errorCode = err.code,
            retakeRequired = OutletProofMessages.requiresRetake(err.code, code)
        )
    }

    private fun transientFailure(userId: String?, payload: OutletProofPayload): OutletProofOutcome {
        if (payload.customerId.isNullOrBlank()) return OutletProofOutcome.NeedsInternet()
        val action = enqueue(userId, payload)
            ?: return OutletProofOutcome.Rejected(OutletProofMessages.COULD_NOT_SAVE_OFFLINE, null, "QUEUE_UNAVAILABLE", false)
        return OutletProofOutcome.SavedOffline(action)
    }

    private fun enqueue(userId: String?, payload: OutletProofPayload): PendingAction? {
        val manager = queue ?: return null
        if (userId.isNullOrBlank()) return null
        // One pending proof per employee per outlet on the server: a newer capture supersedes an unsent older one.
        manager.getQueueForUser(userId)
            .filter {
                it.isOutletProof && it.outletProofPayload?.customerId == payload.customerId &&
                    it.outletProofPayload?.idempotencyKey != payload.idempotencyKey
            }
            .forEach { old ->
                manager.removeAction(old.id)
                old.outletProofPayload?.photoPath?.takeIf { it != payload.photoPath }?.let(deleteFile)
            }
        val action = PendingAction(
            userId = userId,
            visitId = payload.customerId.orEmpty(),
            actionType = PendingAction.TYPE_OUTLET_PROOF,
            latitude = payload.latitude ?: 0.0,
            longitude = payload.longitude ?: 0.0,
            timestamp = payload.capturedAtEpochMs ?: System.currentTimeMillis(),
            accuracyM = payload.accuracyM,
            isMockLocation = payload.isMock,
            outletProofPayload = payload
        )
        manager.enqueueAction(action)
        return action
    }
}

/** Rep-facing texts for outlet-proof failures. Pure so they are unit-tested. */
object OutletProofMessages {
    const val NEW_OUTLET_NEEDS_INTERNET =
        "Internet needed to add a new outlet. Connect to the internet and try again (retake the photo if it is more than 2 minutes old)."
    const val PHOTO_MISSING = "The photo file is missing on this device. Please retake it at the outlet."
    const val COULD_NOT_SAVE_OFFLINE = "Could not save the photo on this device. Please try again."
    const val STALE_CAPTURE = "Photo was taken too long ago to verify. Please retake it at the outlet."
    const val QUEUED_OFFLINE =
        "No internet. Saved on this device and it will be submitted when connectivity returns. " +
            "Note: the server only accepts a photo taken within the last 3 minutes, so if you stay offline longer " +
            "you will be asked to retake it at the outlet."

    private val RETAKE_CODES = setOf(
        "OUTLET_PROOF_MOCK_LOCATION", "OUTLET_PROOF_ACCURACY_TOO_LOW", "OUTLET_PROOF_STALE_CAPTURE",
        "OUTLET_PROOF_FUTURE_CAPTURE", "OUTLET_PROOF_DUPLICATE_IMAGE", "OUTLET_PROOF_INVALID_IMAGE",
        "OUTLET_PROOF_IMAGE_TOO_LARGE", "OUTLET_PROOF_OUTSIDE_INDIA", "OUTLET_PROOF_COORDINATES_REQUIRED",
        "OUTLET_PROOF_ACCURACY_REQUIRED", "OUTLET_PROOF_CAPTURED_AT_REQUIRED", "OUTLET_PROOF_CAPTURED_AT_INVALID",
        "OUTLET_PROOF_MOCK_FLAG_REQUIRED", "PHOTO_MISSING"
    )

    fun requiresRetake(errorCode: String?, httpStatus: Int?): Boolean =
        errorCode in RETAKE_CODES || httpStatus == 415 || httpStatus == 413

    fun forCode(errorCode: String?, httpStatus: Int?, serverMessage: String?): String = when {
        errorCode == "OUTLET_PROOF_MOCK_LOCATION" ->
            "Mock/fake location detected. Turn off any mock-location app and retake the photo at the outlet."
        errorCode == "OUTLET_PROOF_ACCURACY_TOO_LOW" ->
            "GPS accuracy was too low (it must be within 30 m). Move to open sky and retake the photo."
        errorCode == "OUTLET_PROOF_STALE_CAPTURE" -> STALE_CAPTURE
        errorCode == "OUTLET_PROOF_FUTURE_CAPTURE" ->
            "Your phone's clock looks wrong (photo time is in the future). Set the date and time to automatic, then retake the photo."
        errorCode == "OUTLET_PROOF_DUPLICATE_IMAGE" ->
            "This photo was already used for another outlet. Take a fresh live photo of this outlet."
        errorCode == "OUTLET_PROOF_ALREADY_PENDING" ->
            "You already sent a photo for this outlet. It is waiting for admin review."
        errorCode == "OUTLET_PROOF_ALREADY_CONFIRMED" ->
            "You already confirmed this outlet's location."
        errorCode == "OUTLET_PROOF_OUTSIDE_INDIA" ->
            "The GPS position is outside India. Check your location and retake the photo at the outlet."
        errorCode == "OUTLET_PROOF_IMAGE_TOO_LARGE" || httpStatus == 413 ->
            "The photo is too large to upload. Please retake it."
        errorCode == "OUTLET_PROOF_INVALID_IMAGE" || httpStatus == 415 ->
            "The photo could not be read. Please retake it."
        httpStatus == 404 -> HttpErrors.NOT_AVAILABLE_MESSAGE
        errorCode == "OUTLET_PROOF_EXPIRED" -> "The outlet photo expired (it is only valid for 48 hours). Please retake it."
        !serverMessage.isNullOrBlank() -> serverMessage
        else -> ApiErrorParser.defaultUserMessage(httpStatus ?: 0)
    }

    /** Result line for a stored proof (status the rep sees after an upload / queue sync). */
    fun describeResult(proof: OutletProofRead): String {
        val distance = proof.distanceFromVerifiedM
            ?.let { " (%.0f m from the verified location)".format(Locale.US, it) }.orEmpty()
        return when {
            proof.status == "CONFIRMED" || proof.kind == "CONFIRMATION" ->
                "Location confirmed. Your photo and GPS match the verified outlet location."
            proof.kind == "CHANGE_REQUEST" ->
                "Change request sent$distance. An admin will review the new location before it replaces the old one."
            proof.status == "APPROVED" -> "Approved by admin."
            proof.status == "REJECTED" -> "Rejected by admin" + (proof.rejectionReason?.let { ": $it" } ?: ".")
            proof.status == "UNATTACHED" -> "Photo uploaded. Now submit the outlet."
            else -> "Photo and GPS sent. Pending admin approval."
        }
    }
}
