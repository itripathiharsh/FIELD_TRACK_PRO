package com.fieldtrackpro.android.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.DashboardSummaryDto
import com.fieldtrackpro.android.data.model.VisitDto
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.data.repository.VisitRepository
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed class VisitsState {
    object Loading : VisitsState()
    data class Success(
        val visits: List<VisitDto>,
        val isTodayTab: Boolean = true,
        val totalCount: Int = 0,
        val hasMore: Boolean = false
    ) : VisitsState()
    data class Error(val message: String) : VisitsState()
}

sealed class DashboardState {
    object Loading : DashboardState()
    data class Success(val summary: DashboardSummaryDto) : DashboardState()
    data class Error(val message: String) : DashboardState()
}

enum class VisitTab {
    TODAY,
    ALL
}

/**
 * Visits & Dashboard ViewModel.
 *
 * APP-NAV-003: Loads dedicated backend dashboard aggregate KPIs.
 * APP-NAV-004: Supports server-side pagination with skip/limit and deduplication.
 * APP-PERF-001: 350ms search debounce and previous query Job cancellation.
 */
class VisitsViewModel(
    private val tokenManager: TokenManager,
    private val offlineQueueManager: OfflineQueueManager
) : ViewModel() {

    private val repository = VisitRepository(
        visitApi = ApiClient.createVisitApi(tokenManager),
        customerApi = ApiClient.createCustomerApi(tokenManager),
        geoApi = ApiClient.createGeoApi(tokenManager),
        offlineQueueManager = offlineQueueManager,
        dashboardApi = ApiClient.createDashboardApi(tokenManager),
        tokenManager = tokenManager
    )

    private val _visitsState = MutableStateFlow<VisitsState>(VisitsState.Loading)
    val visitsState: StateFlow<VisitsState> = _visitsState.asStateFlow()

    private val _dashboardState = MutableStateFlow<DashboardState>(DashboardState.Loading)
    val dashboardState: StateFlow<DashboardState> = _dashboardState.asStateFlow()

    private val _selectedTab = MutableStateFlow(VisitTab.TODAY)
    val selectedTab: StateFlow<VisitTab> = _selectedTab.asStateFlow()

    private val _selectedStatus = MutableStateFlow<String?>(null)
    val selectedStatus: StateFlow<String?> = _selectedStatus.asStateFlow()

    private val _searchQuery = MutableStateFlow("")
    val searchQuery: StateFlow<String> = _searchQuery.asStateFlow()

    private val _pendingOfflineCount = MutableStateFlow(0)
    val pendingOfflineCount: StateFlow<Int> = _pendingOfflineCount.asStateFlow()

    private var currentSkip = 0
    private val pageSize = 50
    private var hasMorePages = true
    private var isLoadingPage = false
    private val accumulatedVisits = mutableListOf<VisitDto>()

    private var searchJob: Job? = null
    private var loadJob: Job? = null

    fun setTab(tab: VisitTab) {
        searchJob?.cancel()
        _selectedTab.value = tab
        currentSkip = 0
        hasMorePages = true
        accumulatedVisits.clear()
        loadVisits()
    }

    fun setStatusFilter(status: String?) {
        searchJob?.cancel()
        _selectedStatus.value = if (status == "ALL") null else status
        currentSkip = 0
        hasMorePages = true
        accumulatedVisits.clear()
        loadVisits()
    }

    fun setSearchQuery(query: String) {
        _searchQuery.value = query
        searchJob?.cancel()
        searchJob = viewModelScope.launch {
            delay(350)
            currentSkip = 0
            hasMorePages = true
            accumulatedVisits.clear()
            loadVisits()
        }
    }

    fun loadVisits(refresh: Boolean = false) {
        if (refresh) {
            loadJob?.cancel()
            currentSkip = 0
            hasMorePages = true
            accumulatedVisits.clear()
            isLoadingPage = false
        }
        if (isLoadingPage) return
        isLoadingPage = true

        loadJob?.cancel()
        loadJob = viewModelScope.launch {
            if (accumulatedVisits.isEmpty()) {
                _visitsState.value = VisitsState.Loading
            }
            updateOfflineCount()

            val tab = _selectedTab.value
            val status = _selectedStatus.value
            val query = _searchQuery.value.takeIf { it.isNotBlank() }

            val result = if (tab == VisitTab.TODAY) {
                repository.getTodayVisits(status = status, search = query, skip = currentSkip, limit = pageSize)
            } else {
                repository.getVisits(status = status, search = query, skip = currentSkip, limit = pageSize)
            }

            when (result) {
                is Resource.Success -> {
                    val newVisits = result.data
                    hasMorePages = newVisits.size >= pageSize
                    if (currentSkip == 0) {
                        accumulatedVisits.clear()
                    }
                    // Deduplicate by ID
                    val existingIds = accumulatedVisits.map { it.id }.toSet()
                    for (v in newVisits) {
                        if (v.id !in existingIds) {
                            accumulatedVisits.add(v)
                        }
                    }
                    currentSkip += newVisits.size

                    _visitsState.value = VisitsState.Success(
                        visits = accumulatedVisits.toList(),
                        isTodayTab = (tab == VisitTab.TODAY),
                        totalCount = accumulatedVisits.size,
                        hasMore = hasMorePages
                    )
                }
                is Resource.Error -> {
                    if (accumulatedVisits.isEmpty()) {
                        _visitsState.value = VisitsState.Error(result.message)
                    }
                }
                else -> {}
            }
            isLoadingPage = false
        }
    }

    fun loadNextPage() {
        if (!hasMorePages || isLoadingPage) return
        loadVisits()
    }

    fun loadDashboardSummary() {
        viewModelScope.launch {
            _dashboardState.value = DashboardState.Loading
            updateOfflineCount()
            when (val result = repository.getDashboardSummary()) {
                is Resource.Success -> _dashboardState.value = DashboardState.Success(result.data)
                is Resource.Error -> _dashboardState.value = DashboardState.Error(result.message)
                else -> {}
            }
        }
    }

    fun updateOfflineCount() {
        val currentUserId = tokenManager.getUserId()
        _pendingOfflineCount.value = offlineQueueManager.getQueueForUser(currentUserId).size
    }

    fun syncOfflineQueue(onComplete: (Int) -> Unit = {}) {
        viewModelScope.launch {
            val currentUserId = tokenManager.getUserId()
            val result = repository.syncOfflineQueue(activeUserId = currentUserId)
            updateOfflineCount()
            loadVisits()
            onComplete(result.syncedCount)
        }
    }

    fun clearState() {
        searchJob?.cancel()
        loadJob?.cancel()
        currentSkip = 0
        hasMorePages = true
        accumulatedVisits.clear()
        _visitsState.value = VisitsState.Loading
        _dashboardState.value = DashboardState.Loading
    }
}
