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
    data class Success(
        val visits: List<VisitDto>,
        val isTodayTab: Boolean = true,
        val totalCount: Int = 0
    ) : VisitsState()
    data class Error(val message: String) : VisitsState()
}

enum class VisitTab {
    TODAY,
    ALL
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

    private val _selectedTab = MutableStateFlow(VisitTab.TODAY)
    val selectedTab: StateFlow<VisitTab> = _selectedTab.asStateFlow()

    private val _selectedStatus = MutableStateFlow<String?>(null)
    val selectedStatus: StateFlow<String?> = _selectedStatus.asStateFlow()

    private val _searchQuery = MutableStateFlow("")
    val searchQuery: StateFlow<String> = _searchQuery.asStateFlow()

    private val _pendingOfflineCount = MutableStateFlow(0)
    val pendingOfflineCount: StateFlow<Int> = _pendingOfflineCount.asStateFlow()

    fun setTab(tab: VisitTab) {
        _selectedTab.value = tab
        loadVisits()
    }

    fun setStatusFilter(status: String?) {
        _selectedStatus.value = if (status == "ALL") null else status
        loadVisits()
    }

    fun setSearchQuery(query: String) {
        _searchQuery.value = query
        loadVisits()
    }

    fun loadVisits() {
        viewModelScope.launch {
            _visitsState.value = VisitsState.Loading
            updateOfflineCount()

            val tab = _selectedTab.value
            val status = _selectedStatus.value
            val query = _searchQuery.value.takeIf { it.isNotBlank() }

            val result = if (tab == VisitTab.TODAY) {
                repository.getTodayVisits(status = status, search = query)
            } else {
                repository.getVisits(status = status, search = query)
            }

            when (result) {
                is Resource.Success -> {
                    _visitsState.value = VisitsState.Success(
                        visits = result.data,
                        isTodayTab = (tab == VisitTab.TODAY),
                        totalCount = result.data.size
                    )
                }
                is Resource.Error -> {
                    _visitsState.value = VisitsState.Error(result.message)
                }
                else -> {}
            }
        }
    }

    fun updateOfflineCount() {
        _pendingOfflineCount.value = offlineQueueManager.getQueue().size
    }

    fun syncOfflineQueue(onComplete: (Int) -> Unit) {
        viewModelScope.launch {
            val result = repository.syncOfflineQueue()
            updateOfflineCount()
            loadVisits()
            onComplete(result.syncedCount)
        }
    }
}
