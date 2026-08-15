package com.fieldtrackpro.android.ui.viewmodel

import android.app.Application
import android.util.Base64
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.work.WorkManager
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.SignatureDto
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.data.repository.SignatureRepository
import com.fieldtrackpro.android.workers.UploadRetryPolicy
import com.fieldtrackpro.android.workers.UploadRetryScheduler
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.util.UUID

sealed class SignatureState {
    object Idle : SignatureState()
    object Loading : SignatureState()
    data class ListSuccess(val items: List<SignatureDto>) : SignatureState()
    data class UploadSuccess(val signature: SignatureDto) : SignatureState()
    /** P1-6: queued for automatic WorkManager retry rather than lost - see MediaState.QueuedForRetry. */
    data class QueuedForRetry(val message: String) : SignatureState()
    data class Error(val message: String) : SignatureState()
}

class SignatureViewModel(application: Application, tokenManager: TokenManager) : AndroidViewModel(application) {

    private val repository = SignatureRepository(ApiClient.createSignatureApi(tokenManager))

    private val _signatureState = MutableStateFlow<SignatureState>(SignatureState.Idle)
    val signatureState: StateFlow<SignatureState> = _signatureState.asStateFlow()

    fun loadVisitSignatures(visitId: String) {
        viewModelScope.launch {
            _signatureState.value = SignatureState.Loading
            when (val res = repository.getVisitSignatures(visitId)) {
                is Resource.Success -> _signatureState.value = SignatureState.ListSuccess(res.data)
                is Resource.Error -> _signatureState.value = SignatureState.Error(res.message)
                else -> {}
            }
        }
    }

    fun uploadSignature(visitId: String, signatureType: String, imageBytes: ByteArray, captureMethod: String = "SIGNATURE") {
        viewModelScope.launch {
            uploadSignatureAwait(visitId, signatureType, imageBytes, captureMethod)
        }
    }

    /**
     * Uploads a signature/acknowledgement and suspends until the result is
     * known, so a caller can wait for completion before navigating away.
     *
     * Durability: [imageBytes] is persisted to a durable file and a
     * WorkManager safety-net retry is scheduled BEFORE the direct upload is
     * even attempted - so the capture survives even if the app process dies
     * the instant after this is called, not only if the direct attempt
     * happens to fail while the app is still alive to notice. If the direct
     * attempt succeeds, the safety-net job is cancelled as redundant.
     *
     * @return true if the upload succeeded outright. A transient failure that
     * gets queued for background retry (P1-6) returns false here too - the
     * caller still shouldn't navigate away treating it as a success - but
     * `signatureState` distinguishes [SignatureState.QueuedForRetry] from a
     * permanent [SignatureState.Error] for the UI.
     */
    suspend fun uploadSignatureAwait(
        visitId: String,
        signatureType: String,
        imageBytes: ByteArray,
        captureMethod: String = "SIGNATURE",
    ): Boolean {
        _signatureState.value = SignatureState.Loading
        val uniqueWorkName = "signature_upload_${UUID.randomUUID()}"
        UploadRetryScheduler.queueSignatureUpload(
            context = getApplication(), uniqueWorkName = uniqueWorkName,
            visitId = visitId, signatureType = signatureType, captureMethod = captureMethod,
            imageBytes = imageBytes,
        )

        val base64 = Base64.encodeToString(imageBytes, Base64.NO_WRAP)
        return when (val res = repository.uploadSignature(visitId, signatureType, base64, captureMethod)) {
            is Resource.Success -> {
                cancelSafetyNet(uniqueWorkName)
                _signatureState.value = SignatureState.UploadSuccess(res.data)
                true
            }
            is Resource.Error -> {
                if (UploadRetryPolicy.isTransientFailure(res.message)) {
                    // Safety-net job already scheduled above - nothing more to do.
                    _signatureState.value = SignatureState.QueuedForRetry("Upload failed - queued for automatic retry: ${res.message}")
                } else {
                    // A permanent rejection (bad image, duplicate, etc.) will
                    // never succeed on retry either - cancel the safety net
                    // so it doesn't waste a network round trip repeating it.
                    cancelSafetyNet(uniqueWorkName)
                    _signatureState.value = SignatureState.Error(res.message)
                }
                false
            }
            else -> false
        }
    }

    /** Same durability/cancel-on-success pattern as [uploadSignatureAwait], for correcting an existing capture. */
    suspend fun replaceSignatureAwait(
        visitId: String,
        signatureId: String,
        imageBytes: ByteArray,
        captureMethod: String = "SIGNATURE",
    ): Boolean {
        _signatureState.value = SignatureState.Loading
        val uniqueWorkName = "signature_replace_${signatureId}_${UUID.randomUUID()}"
        UploadRetryScheduler.queueSignatureUpload(
            context = getApplication(), uniqueWorkName = uniqueWorkName,
            visitId = visitId, signatureType = "", captureMethod = captureMethod,
            imageBytes = imageBytes, signatureId = signatureId,
        )

        val base64 = Base64.encodeToString(imageBytes, Base64.NO_WRAP)
        return when (val res = repository.replaceSignature(visitId, signatureId, base64, captureMethod)) {
            is Resource.Success -> {
                cancelSafetyNet(uniqueWorkName)
                _signatureState.value = SignatureState.UploadSuccess(res.data)
                true
            }
            is Resource.Error -> {
                if (UploadRetryPolicy.isTransientFailure(res.message)) {
                    _signatureState.value = SignatureState.QueuedForRetry("Replace failed - queued for automatic retry: ${res.message}")
                } else {
                    cancelSafetyNet(uniqueWorkName)
                    _signatureState.value = SignatureState.Error(res.message)
                }
                false
            }
            else -> false
        }
    }

    private fun cancelSafetyNet(uniqueWorkName: String) {
        WorkManager.getInstance(getApplication()).cancelUniqueWork(uniqueWorkName)
    }
}
