package com.fieldtrackpro.android.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.data.model.GeoVerificationLogDto
import com.fieldtrackpro.android.data.model.VisitDto
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.data.repository.VisitRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed class VisitDetailState {
    object Loading : VisitDetailState()
    data class Success(
        val visit: VisitDto,
        val geoLogs: List<GeoVerificationLogDto> = emptyList(),
        val customer: CustomerDto? = null
    ) : VisitDetailState()
    data class Error(val message: String) : VisitDetailState()
}

/**
 * ViewModel for Visit Details Screen.
 *
 * APP-CUST-004 / 005 / 019: Eliminates duplicate/N+1 customer API fetches by using
 * the denormalized customer summary and coordinates provided directly within VisitDto.
 */
class VisitDetailsViewModel(
    tokenManager: TokenManager,
    offlineQueueManager: OfflineQueueManager
) : ViewModel() {

    private val repository = VisitRepository(
        visitApi = ApiClient.createVisitApi(tokenManager),
        customerApi = ApiClient.createCustomerApi(tokenManager),
        geoApi = ApiClient.createGeoApi(tokenManager),
        offlineQueueManager = offlineQueueManager,
        tokenManager = tokenManager
    )

    private val _detailState = MutableStateFlow<VisitDetailState>(VisitDetailState.Loading)
    val detailState: StateFlow<VisitDetailState> = _detailState.asStateFlow()

    fun loadVisitDetails(visitId: String) {
        viewModelScope.launch {
            _detailState.value = VisitDetailState.Loading
            when (val visitRes = repository.getVisitById(visitId)) {
                is Resource.Success -> {
                    val logsRes = repository.getVisitGeoLogs(visitId)
                    val logs = if (logsRes is Resource.Success) logsRes.data else emptyList()

                    // APP-CUST-004: Reuse customer summary directly from the visit payload
                    val customer = visitRes.data.toCustomerSummaryDto()

                    _detailState.value = VisitDetailState.Success(visitRes.data, logs, customer)
                }
                is Resource.Error -> _detailState.value = VisitDetailState.Error(visitRes.message)
                else -> {}
            }
        }
    }

    fun clearState() {
        _detailState.value = VisitDetailState.Loading
    }
}
