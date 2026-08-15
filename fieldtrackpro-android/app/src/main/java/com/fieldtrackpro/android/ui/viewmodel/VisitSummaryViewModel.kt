package com.fieldtrackpro.android.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.GeoVerificationLogDto
import com.fieldtrackpro.android.data.model.MediaDto
import com.fieldtrackpro.android.data.model.VisitDto
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.MediaRepository
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.data.repository.VisitRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed class VisitSummaryState {
    object Loading : VisitSummaryState()
    data class Ready(
        val visit: VisitDto,
        val media: List<MediaDto> = emptyList(),
        val geoLogs: List<GeoVerificationLogDto> = emptyList()
    ) : VisitSummaryState()
    data class Error(val message: String) : VisitSummaryState()
}

class VisitSummaryViewModel(
    tokenManager: TokenManager,
    offlineQueueManager: OfflineQueueManager
) : ViewModel() {

    private val visitRepository = VisitRepository(
        visitApi = ApiClient.createVisitApi(tokenManager),
        customerApi = ApiClient.createCustomerApi(tokenManager),
        geoApi = ApiClient.createGeoApi(tokenManager),
        offlineQueueManager = offlineQueueManager
    )
    private val mediaRepository = MediaRepository(ApiClient.createMediaApi(tokenManager))

    private val _summaryState = MutableStateFlow<VisitSummaryState>(VisitSummaryState.Loading)
    val summaryState: StateFlow<VisitSummaryState> = _summaryState.asStateFlow()

    fun loadVisitSummary(visitId: String) {
        viewModelScope.launch {
            _summaryState.value = VisitSummaryState.Loading

            when (val visitResult = visitRepository.getVisitById(visitId)) {
                is Resource.Success -> {
                    val visit = visitResult.data

                    // Load media
                    val media = when (val mediaResult = mediaRepository.getVisitMedia(visitId)) {
                        is Resource.Success -> mediaResult.data
                        else -> emptyList()
                    }

                    // Load geo logs
                    val geoLogs = when (val logsResult = visitRepository.getVisitGeoLogs(visitId)) {
                        is Resource.Success -> logsResult.data
                        else -> emptyList()
                    }

                    _summaryState.value = VisitSummaryState.Ready(visit, media, geoLogs)
                }
                is Resource.Error -> {
                    _summaryState.value = VisitSummaryState.Error(visitResult.message)
                }
                else -> {}
            }
        }
    }
}
