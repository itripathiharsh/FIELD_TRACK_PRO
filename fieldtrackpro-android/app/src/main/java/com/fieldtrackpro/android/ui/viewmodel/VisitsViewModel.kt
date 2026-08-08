package com.fieldtrackpro.android.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.VisitDto
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.data.repository.VisitRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed class VisitsState {
    object Loading : VisitsState()
    data class Success(val visits: List<VisitDto>) : VisitsState()
    data class Error(val message: String) : VisitsState()
}

class VisitsViewModel(
    tokenManager: TokenManager,
    private val offlineQueueManager: OfflineQueueManager
) : ViewModel() {

    private val repository = VisitRepository(
        visitApi = ApiClient.createVisitApi(tokenManager),
        customerApi = ApiClient.createCustomerApi(tokenManager),
        geoApi = ApiClient.createGeoApi(tokenManager),
        offlineQueueManager = offlineQueueManager
    )

    private val _visitsState = MutableStateFlow<VisitsState>(VisitsState.Loading)
    val visitsState: StateFlow<VisitsState> = _visitsState.asStateFlow()

    private val _pendingOfflineCount = MutableStateFlow(0)
    val pendingOfflineCount: StateFlow<Int> = _pendingOfflineCount.asStateFlow()

    fun loadVisits(filterStatus: String? = null) {
        viewModelScope.launch {
            _visitsState.value = VisitsState.Loading
            updateOfflineCount()
            when (val result = repository.getVisits(filterStatus)) {
                is Resource.Success -> _visitsState.value = VisitsState.Success(result.data)
                is Resource.Error -> _visitsState.value = VisitsState.Error(result.message)
                else -> {}
            }
        }
    }

    fun updateOfflineCount() {
        _pendingOfflineCount.value = offlineQueueManager.getQueue().size
    }

    fun syncOfflineQueue(onComplete: (Int) -> Unit) {
        viewModelScope.launch {
            val count = repository.syncOfflineQueue()
            updateOfflineCount()
            loadVisits()
            onComplete(count)
        }
    }
}
