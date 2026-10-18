package com.fieldtrackpro.android.ui.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.OutletProofDraftStore
import com.fieldtrackpro.android.data.local.OutletProofPayload
import com.fieldtrackpro.android.data.local.OutletProofStore
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.OutletProofRead
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.OutletProofMessages
import com.fieldtrackpro.android.data.repository.OutletProofOutcome
import com.fieldtrackpro.android.data.repository.OutletProofSubmitter
import com.fieldtrackpro.android.utils.OutletProofRules
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/** What the outlet photo card / dialog shows. */
sealed class ProofUi {
    /** Nothing captured yet. */
    object Empty : ProofUi()

    data class Uploading(val payload: OutletProofPayload) : ProofUi()

    /** Stored on the server (new outlet: UNATTACHED, waiting for the prospect submit). */
    data class Uploaded(val payload: OutletProofPayload, val proof: OutletProofRead) : ProofUi()

    /** Existing outlet, offline: saved on the device, uploads when connectivity returns. */
    data class Queued(val payload: OutletProofPayload) : ProofUi()

    /**
     * [canRetry]: the SAME capture can be re-sent (still fresh, e.g. new outlet while offline).
     * [retakeRequired]: only a new photo can fix it.
     */
    data class Failed(
        val message: String,
        val payload: OutletProofPayload?,
        val canRetry: Boolean,
        val retakeRequired: Boolean
    ) : ProofUi()
}

/**
 * Owns one outlet-proof flow (new outlet, or one existing outlet): persists the capture draft, uploads it through
 * [OutletProofSubmitter] and exposes the result. Survives rotation (ViewModel); a process death keeps the draft in
 * [OutletProofDraftStore] so the same idempotency key / uploaded proof id is picked up again by [start].
 */
class OutletProofFlowViewModel(application: Application) : AndroidViewModel(application) {

    private val tokenManager = TokenManager.getInstance(application)
    private val draftStore = OutletProofDraftStore.create(application)
    private val submitter by lazy {
        OutletProofSubmitter(
            api = ApiClient.createOutletProofApi(tokenManager),
            queue = OfflineQueueManager.getInstance(application)
        )
    }

    private val _ui = MutableStateFlow<ProofUi>(ProofUi.Empty)
    val ui: StateFlow<ProofUi> = _ui.asStateFlow()

    private var customerId: String? = null
    private var outletName: String? = null
    private var started = false
    private var consumed = false

    private fun userId(): String? = tokenManager.getUserId()

    /**
     * Binds the flow to an outlet (null = new outlet) and restores a draft left by a process death.
     * [resetTerminal]: for the existing-outlet dialog, forget a previous finished result when it is opened again.
     */
    fun start(customerId: String?, outletName: String?, resetTerminal: Boolean = false) {
        if (started && this.customerId == customerId) {
            val cur = _ui.value
            if (resetTerminal && (cur is ProofUi.Uploaded || cur is ProofUi.Queued)) _ui.value = ProofUi.Empty
            return
        }
        started = true
        this.customerId = customerId
        this.outletName = outletName
        val uid = userId() ?: return
        val draft = draftStore.get(uid, customerId) ?: return
        val now = System.currentTimeMillis()
        val file = draft.photoPath?.let { File(it) }
        when {
            draft.serverProofId != null && customerId == null &&
                OutletProofRules.isUnattachedProofUsable(draft.uploadedAtEpochMs, now) &&
                file?.isFile == true ->
                _ui.value = ProofUi.Uploaded(draft, OutletProofRead(id = draft.serverProofId, status = "UNATTACHED"))
            file?.isFile == true && OutletProofRules.isUploadFresh(draft.capturedAtEpochMs, now) ->
                upload(draft)
            else -> {
                // Stale or file gone: the server would reject it; only a new photo helps.
                discardFiles(draft)
                draftStore.clear(uid, customerId)
                _ui.value = ProofUi.Failed(OutletProofMessages.STALE_CAPTURE, null, canRetry = false, retakeRequired = true)
            }
        }
    }

    /** Called when the capture screen confirms "Use photo". The payload carries the key generated at the shutter. */
    fun onCaptured(payload: OutletProofPayload) {
        val uid = userId()
        if (uid != null) draftStore.save(uid, payload)
        upload(payload)
    }

    fun retryUpload() {
        val cur = _ui.value
        val payload = (cur as? ProofUi.Failed)?.payload ?: return
        if (!OutletProofRules.isUploadFresh(payload.capturedAtEpochMs, System.currentTimeMillis())) {
            discardFiles(payload)
            userId()?.let { draftStore.clear(it, customerId) }
            _ui.value = ProofUi.Failed(OutletProofMessages.STALE_CAPTURE, null, canRetry = false, retakeRequired = true)
            return
        }
        upload(payload)
    }

    private fun upload(payload: OutletProofPayload) {
        _ui.value = ProofUi.Uploading(payload)
        viewModelScope.launch {
            val uid = userId()
            val outcome = withContext(Dispatchers.IO) { submitter.submit(uid, payload) }
            val isNew = payload.customerId.isNullOrBlank()
            when (outcome) {
                is OutletProofOutcome.Uploaded -> {
                    if (isNew) {
                        val stored = payload.copy(serverProofId = outcome.proof.id, uploadedAtEpochMs = System.currentTimeMillis())
                        if (uid != null) draftStore.save(uid, stored)
                        _ui.value = ProofUi.Uploaded(stored, outcome.proof)
                    } else {
                        // Existing outlet: the server has it; the local photo and draft are no longer needed.
                        discardFiles(payload)
                        if (uid != null) draftStore.clear(uid, customerId)
                        _ui.value = ProofUi.Uploaded(payload.copy(photoPath = null), outcome.proof)
                    }
                }
                is OutletProofOutcome.SavedOffline -> {
                    // The offline queue owns the file now.
                    if (uid != null) draftStore.clear(uid, customerId)
                    _ui.value = ProofUi.Queued(payload)
                }
                is OutletProofOutcome.NeedsInternet ->
                    _ui.value = ProofUi.Failed(outcome.message, payload, canRetry = true, retakeRequired = false)
                is OutletProofOutcome.Rejected -> {
                    // A rejected photo can never be re-sent as is.
                    discardFiles(payload)
                    if (uid != null) draftStore.clear(uid, customerId)
                    _ui.value = ProofUi.Failed(outcome.message, null, canRetry = false, retakeRequired = outcome.retakeRequired)
                }
            }
        }
    }

    /** User chose "Retake" / "Remove": drops the current capture (file + draft) and returns to Empty. */
    fun discard() {
        val payload = when (val cur = _ui.value) {
            is ProofUi.Uploading -> cur.payload
            is ProofUi.Uploaded -> cur.payload
            is ProofUi.Failed -> cur.payload
            else -> null
        }
        payload?.let { discardFiles(it) }
        userId()?.let { draftStore.clear(it, customerId) }
        _ui.value = ProofUi.Empty
    }

    /** The prospect was created with this proof: the photo and draft have served their purpose. */
    fun onConsumed() {
        consumed = true
        discard()
    }

    private fun discardFiles(payload: OutletProofPayload) {
        OutletProofStore.delete(payload.photoPath)
    }

    override fun onCleared() {
        // The screen is gone for good (NOT a rotation, NOT a process death): do not leave a stale capture around
        // that could be mistaken for the next outlet's photo.
        if (!consumed && _ui.value !is ProofUi.Queued) {
            val cur = _ui.value
            val payload = when (cur) {
                is ProofUi.Uploaded -> cur.payload
                is ProofUi.Failed -> cur.payload
                is ProofUi.Uploading -> cur.payload
                else -> null
            }
            if (payload != null && customerId == null) {
                discardFiles(payload)
                userId()?.let { draftStore.clear(it, customerId) }
            }
        }
        super.onCleared()
    }
}
