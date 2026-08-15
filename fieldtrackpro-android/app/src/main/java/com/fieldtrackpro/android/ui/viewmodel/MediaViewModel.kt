package com.fieldtrackpro.android.ui.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.MediaDto
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.MediaRepository
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.workers.UploadRetryPolicy
import com.fieldtrackpro.android.workers.UploadRetryScheduler
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed class MediaState {
    object Idle : MediaState()
    object Loading : MediaState()
    data class ListSuccess(val items: List<MediaDto>) : MediaState()
    data class UploadSuccess(val media: MediaDto) : MediaState()
    /** P1-6: a direct upload attempt failed transiently and was handed to
     * WorkManager for automatic background retry - distinct from a
     * permanent [Error] so the UI can tell the rep their photo is not lost. */
    data class QueuedForRetry(val message: String) : MediaState()
    data class Error(val message: String) : MediaState()
}

class MediaViewModel(application: Application, tokenManager: TokenManager) : AndroidViewModel(application) {

    private val repository = MediaRepository(ApiClient.createMediaApi(tokenManager))

    private val _mediaState = MutableStateFlow<MediaState>(MediaState.Idle)
    val mediaState: StateFlow<MediaState> = _mediaState.asStateFlow()

    /** Surfaces a client-side failure (e.g. couldn't read the picked file) through the same state the UI already renders errors from. */
    fun reportError(message: String) {
        _mediaState.value = MediaState.Error(message)
    }

    fun loadVisitMedia(visitId: String) {
        viewModelScope.launch {
            _mediaState.value = MediaState.Loading
            when (val res = repository.getVisitMedia(visitId)) {
                is Resource.Success -> _mediaState.value = MediaState.ListSuccess(res.data)
                is Resource.Error -> _mediaState.value = MediaState.Error(res.message)
                else -> {}
            }
        }
    }

    fun uploadMedia(visitId: String, fileName: String, mimeType: String, fileBytes: ByteArray) {
        viewModelScope.launch {
            _mediaState.value = MediaState.Loading
            when (val res = repository.uploadVisitMedia(visitId, fileName, mimeType, fileBytes)) {
                is Resource.Success -> {
                    _mediaState.value = MediaState.UploadSuccess(res.data)
                    loadVisitMedia(visitId)
                }
                is Resource.Error -> handleUploadFailure(res.message, visitId, fileName, mimeType, fileBytes)
                else -> {}
            }
        }
    }

    /** P2-B: order capture - reuses the media upload pipeline with is_order=true. */
    fun captureOrder(visitId: String, fileName: String, mimeType: String, fileBytes: ByteArray, note: String?) {
        viewModelScope.launch {
            _mediaState.value = MediaState.Loading
            when (val res = repository.uploadOrderCapture(visitId, fileName, mimeType, fileBytes, note)) {
                is Resource.Success -> {
                    _mediaState.value = MediaState.UploadSuccess(res.data)
                    loadVisitMedia(visitId)
                }
                is Resource.Error -> handleUploadFailure(res.message, visitId, fileName, mimeType, fileBytes, isOrder = true, note = note)
                else -> {}
            }
        }
    }

    /**
     * P1-6: a failed direct upload is queued for a background WorkManager
     * retry when the failure looks transient (network/server, not a
     * validation/auth rejection that would fail identically every time).
     */
    private fun handleUploadFailure(
        errorMessage: String,
        visitId: String,
        fileName: String,
        mimeType: String,
        fileBytes: ByteArray,
        isOrder: Boolean = false,
        note: String? = null,
    ) {
        if (UploadRetryPolicy.isTransientFailure(errorMessage)) {
            val queued = UploadRetryScheduler.queueMediaUpload(
                context = getApplication(), visitId = visitId, fileName = fileName,
                mimeType = mimeType, fileBytes = fileBytes, isOrder = isOrder, note = note,
            )
            _mediaState.value = if (queued) {
                MediaState.QueuedForRetry("Upload failed - queued for automatic retry: $errorMessage")
            } else {
                MediaState.Error(errorMessage)
            }
        } else {
            _mediaState.value = MediaState.Error(errorMessage)
        }
    }
}
