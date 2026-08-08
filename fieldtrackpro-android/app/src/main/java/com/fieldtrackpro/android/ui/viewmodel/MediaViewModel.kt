package com.fieldtrackpro.android.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.MediaDto
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.MediaRepository
import com.fieldtrackpro.android.data.repository.Resource
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed class MediaState {
    object Idle : MediaState()
    object Loading : MediaState()
    data class ListSuccess(val items: List<MediaDto>) : MediaState()
    data class UploadSuccess(val media: MediaDto) : MediaState()
    data class Error(val message: String) : MediaState()
}

class MediaViewModel(tokenManager: TokenManager) : ViewModel() {

    private val repository = MediaRepository(ApiClient.createMediaApi(tokenManager))

    private val _mediaState = MutableStateFlow<MediaState>(MediaState.Idle)
    val mediaState: StateFlow<MediaState> = _mediaState.asStateFlow()

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
                is Resource.Error -> _mediaState.value = MediaState.Error(res.message)
                else -> {}
            }
        }
    }
}
