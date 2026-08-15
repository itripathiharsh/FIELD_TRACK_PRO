package com.fieldtrackpro.android.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.data.model.GeoVerificationLogDto
import com.fieldtrackpro.android.data.model.VisitDto
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.CustomerRepository
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

class VisitDetailsViewModel(
    tokenManager: TokenManager,
    offlineQueueManager: OfflineQueueManager
) : ViewModel() {

    private val repository = VisitRepository(
        visitApi = ApiClient.createVisitApi(tokenManager),
        customerApi = ApiClient.createCustomerApi(tokenManager),
        geoApi = ApiClient.createGeoApi(tokenManager),
        offlineQueueManager = offlineQueueManager
    )
    private val customerRepository = CustomerRepository(ApiClient.createCustomerApi(tokenManager))

    private val _detailState = MutableStateFlow<VisitDetailState>(VisitDetailState.Loading)
    val detailState: StateFlow<VisitDetailState> = _detailState.asStateFlow()

    fun loadVisitDetails(visitId: String) {
        viewModelScope.launch {
            _detailState.value = VisitDetailState.Loading
            when (val visitRes = repository.getVisitById(visitId)) {
                is Resource.Success -> {
                    val logsRes = repository.getVisitGeoLogs(visitId)
                    val logs = if (logsRes is Resource.Success) logsRes.data else emptyList()

                    // Fetch customer data for geofence setup
                    val customer = when (val custRes = customerRepository.getCustomerById(visitRes.data.customerId)) {
                        is Resource.Success -> custRes.data
                        else -> null
                    }

                    _detailState.value = VisitDetailState.Success(visitRes.data, logs, customer)
                }
                is Resource.Error -> _detailState.value = VisitDetailState.Error(visitRes.message)
                else -> {}
            }
        }
    }
}
