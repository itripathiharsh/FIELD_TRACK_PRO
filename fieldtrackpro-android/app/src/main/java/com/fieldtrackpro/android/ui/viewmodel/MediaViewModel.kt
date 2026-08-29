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
    data class QueuedForRetry(val message: String) : MediaState()
    data class Error(val message: String) : MediaState()
}

class MediaViewModel(application: Application, tokenManager: TokenManager) : AndroidViewModel(application) {

    private val repository = MediaRepository(ApiClient.createMediaApi(tokenManager))

    private val _mediaState = MutableStateFlow<MediaState>(MediaState.Idle)
    val mediaState: StateFlow<MediaState> = _mediaState.asStateFlow()

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
                is Resource.Error -> {
                    if (UploadRetryPolicy.isTransientFailure(res.message)) {
                        UploadRetryScheduler.queueMediaUpload(
                            context = getApplication(),
                            visitId = visitId,
                            fileName = fileName,
                            mimeType = mimeType,
                            fileBytes = fileBytes,
                            isOrder = false,
                            note = null,
                        )
                        _mediaState.value = MediaState.QueuedForRetry("Upload failed - queued for automatic retry: ${res.message}")
                    } else {
                        _mediaState.value = MediaState.Error(res.message)
                    }
                }
                else -> {}
            }
        }
    }

    fun uploadOrderCapture(visitId: String, fileName: String, mimeType: String, fileBytes: ByteArray, note: String?) {
        viewModelScope.launch {
            _mediaState.value = MediaState.Loading
            when (val res = repository.uploadOrderCapture(visitId, fileName, mimeType, fileBytes, note)) {
                is Resource.Success -> {
                    _mediaState.value = MediaState.UploadSuccess(res.data)
                    loadVisitMedia(visitId)
                }
                is Resource.Error -> {
                    if (UploadRetryPolicy.isTransientFailure(res.message)) {
                        UploadRetryScheduler.queueMediaUpload(
                            context = getApplication(),
                            visitId = visitId,
                            fileName = fileName,
                            mimeType = mimeType,
                            fileBytes = fileBytes,
                            isOrder = true,
                            note = note,
                        )
                        _mediaState.value = MediaState.QueuedForRetry("Order capture queued for automatic retry: ${res.message}")
                    } else {
                        _mediaState.value = MediaState.Error(res.message)
                    }
                }
                else -> {}
            }
        }
    }

    fun captureOrder(visitId: String, fileName: String, mimeType: String, fileBytes: ByteArray, note: String?) {
        uploadOrderCapture(visitId, fileName, mimeType, fileBytes, note)
    }

    fun resetState() {
        _mediaState.value = MediaState.Idle
    }
}
