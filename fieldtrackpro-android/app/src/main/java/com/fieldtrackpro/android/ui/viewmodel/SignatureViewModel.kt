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
    data class QueuedForRetry(val message: String) : SignatureState()
    data class Error(val message: String) : SignatureState()
}

class SignatureViewModel(application: Application, tokenManager: TokenManager) : AndroidViewModel(application) {

    private val repository = SignatureRepository(ApiClient.createSignatureApi(tokenManager))

    private val _signatureState = MutableStateFlow<SignatureState>(SignatureState.Idle)
    val signatureState: StateFlow<SignatureState> = _signatureState.asStateFlow()

    val employeeSignatureState = com.fieldtrackpro.android.ui.screens.signature.SignatureCaptureState()
    val customerSignatureState = com.fieldtrackpro.android.ui.screens.signature.SignatureCaptureState()

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
                    _signatureState.value = SignatureState.QueuedForRetry("Upload failed - queued for automatic retry: ${res.message}")
                } else {
                    cancelSafetyNet(uniqueWorkName)
                    _signatureState.value = SignatureState.Error(res.message)
                }
                false
            }
            else -> false
        }
    }

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

    fun resetState() {
        _signatureState.value = SignatureState.Idle
        employeeSignatureState.clear()
        customerSignatureState.clear()
    }
}
