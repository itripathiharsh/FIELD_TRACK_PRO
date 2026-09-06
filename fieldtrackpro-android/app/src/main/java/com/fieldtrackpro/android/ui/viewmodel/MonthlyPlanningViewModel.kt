package com.fieldtrackpro.android.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.data.model.EmployeeMonthlyAnalyticsDto
import com.fieldtrackpro.android.data.model.MonthlyVisitPlanDto
import com.fieldtrackpro.android.data.model.PlannedVisitCreateRequest
import com.fieldtrackpro.android.data.model.PlannedVisitDto
import com.fieldtrackpro.android.data.model.PlannedVisitUpdateRequest
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.CustomerRepository
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.data.repository.VisitPlanningRepository
import kotlinx.coroutines.Job
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.util.Calendar

data class MonthlyPlanUiState(
    val year: Int = Calendar.getInstance().get(Calendar.YEAR),
    val month: Int = Calendar.getInstance().get(Calendar.MONTH) + 1,
    val isLoading: Boolean = false,
    val isSaving: Boolean = false,
    val plan: MonthlyVisitPlanDto? = null,
    val analytics: EmployeeMonthlyAnalyticsDto? = null,
    val selectedFilter: String = "ALL", // ALL, PLANNED, COMPLETED, CALENDAR
    val selectedDate: String? = null,
    val errorMessage: String? = null,
    val successMessage: String? = null,
    val customerSearchResults: List<CustomerDto> = emptyList(),
    val isSearchingCustomers: Boolean = false
) {
    val filteredVisits: List<PlannedVisitDto>
        get() {
            val allVisits = plan?.plannedVisits ?: emptyList()
            return allVisits.filter { visit ->
                when (selectedFilter) {
                    "PLANNED" -> visit.status == "PLANNED"
                    "COMPLETED" -> visit.status == "COMPLETED"
                    "CANCELLED" -> visit.status == "CANCELLED"
                    else -> visit.status != "CANCELLED"
                }
            }
        }
}

class MonthlyPlanningViewModel(
    private val tokenManager: TokenManager? = null,
    customPlanningRepository: VisitPlanningRepository? = null,
    customCustomerRepository: CustomerRepository? = null
) : ViewModel() {

    private val planningRepository: VisitPlanningRepository = customPlanningRepository ?: VisitPlanningRepository(
        ApiClient.createVisitPlanningApi(tokenManager ?: throw IllegalArgumentException("TokenManager must not be null"))
    )

    private val customerRepository: CustomerRepository = customCustomerRepository ?: CustomerRepository(
        ApiClient.createCustomerApi(tokenManager ?: throw IllegalArgumentException("TokenManager must not be null"))
    )

    private val _uiState = MutableStateFlow(MonthlyPlanUiState())
    val uiState: StateFlow<MonthlyPlanUiState> = _uiState.asStateFlow()

    private var customerSearchJob: Job? = null

    init {
        loadMonthlyPlan()
        loadInitialCustomers()
    }

    private fun getDefaultDateForMonth(year: Int, month: Int): String {
        val todayCal = Calendar.getInstance()
        val currentYear = todayCal.get(Calendar.YEAR)
        val currentMonth = todayCal.get(Calendar.MONTH) + 1
        return if (year == currentYear && month == currentMonth) {
            String.format(java.util.Locale.US, "%04d-%02d-%02d", year, month, todayCal.get(Calendar.DAY_OF_MONTH))
        } else {
            String.format(java.util.Locale.US, "%04d-%02d-%02d", year, month, 1)
        }
    }

    fun loadMonthlyPlan(year: Int = _uiState.value.year, month: Int = _uiState.value.month) {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, errorMessage = null, year = year, month = month) }

            val planDeferred = async { planningRepository.getMyPlan(year = year, month = month) }
            val analyticsDeferred = async { planningRepository.getMyMonthAnalytics(year = year, month = month) }

            val planRes = planDeferred.await()
            val analyticsRes = analyticsDeferred.await()

            when (planRes) {
                is Resource.Success -> {
                    val analyticsData = if (analyticsRes is Resource.Success) analyticsRes.data else null
                    _uiState.update {
                        it.copy(
                            isLoading = false,
                            plan = planRes.data,
                            analytics = analyticsData,
                            errorMessage = null
                        )
                    }
                }
                is Resource.Error -> {
                    _uiState.update {
                        it.copy(
                            isLoading = false,
                            errorMessage = planRes.message
                        )
                    }
                }
                is Resource.Loading -> {}
            }
        }
    }

    fun previousMonth() {
        val currentYear = _uiState.value.year
        val currentMonth = _uiState.value.month
        val (newYear, newMonth) = if (currentMonth == 1) {
            Pair(currentYear - 1, 12)
        } else {
            Pair(currentYear, currentMonth - 1)
        }
        val defaultDate = if (_uiState.value.selectedFilter == "CALENDAR") {
            getDefaultDateForMonth(newYear, newMonth)
        } else null
        _uiState.update { it.copy(year = newYear, month = newMonth, selectedDate = defaultDate) }
        loadMonthlyPlan(newYear, newMonth)
    }

    fun nextMonth() {
        val currentYear = _uiState.value.year
        val currentMonth = _uiState.value.month
        val (newYear, newMonth) = if (currentMonth == 12) {
            Pair(currentYear + 1, 1)
        } else {
            Pair(currentYear, currentMonth + 1)
        }
        val defaultDate = if (_uiState.value.selectedFilter == "CALENDAR") {
            getDefaultDateForMonth(newYear, newMonth)
        } else null
        _uiState.update { it.copy(year = newYear, month = newMonth, selectedDate = defaultDate) }
        loadMonthlyPlan(newYear, newMonth)
    }

    fun selectMonth(year: Int, month: Int) {
        val defaultDate = if (_uiState.value.selectedFilter == "CALENDAR") {
            getDefaultDateForMonth(year, month)
        } else null
        _uiState.update { it.copy(year = year, month = month, selectedDate = defaultDate) }
        loadMonthlyPlan(year, month)
    }

    fun setFilter(filter: String) {
        _uiState.update { state ->
            val newDate = if (filter == "CALENDAR" && state.selectedDate == null) {
                getDefaultDateForMonth(state.year, state.month)
            } else state.selectedDate
            state.copy(selectedFilter = filter, selectedDate = newDate)
        }
    }

    fun selectDate(date: String?) {
        _uiState.update { it.copy(selectedDate = date) }
    }

    fun clearMessages() {
        _uiState.update { it.copy(errorMessage = null, successMessage = null) }
    }

    fun loadInitialCustomers() {
        viewModelScope.launch {
            _uiState.update { it.copy(isSearchingCustomers = true) }
            val res = customerRepository.getCustomers(skip = 0, limit = 50)
            if (res is Resource.Success) {
                _uiState.update { it.copy(customerSearchResults = res.data.customers, isSearchingCustomers = false) }
            } else {
                _uiState.update { it.copy(isSearchingCustomers = false) }
            }
        }
    }

    fun searchCustomers(query: String) {
        customerSearchJob?.cancel()
        customerSearchJob = viewModelScope.launch {
            _uiState.update { it.copy(isSearchingCustomers = true) }
            val res = customerRepository.getCustomers(
                skip = 0,
                limit = 50,
                search = query.trim().ifBlank { null }
            )
            if (res is Resource.Success) {
                _uiState.update { it.copy(customerSearchResults = res.data.customers, isSearchingCustomers = false) }
            } else {
                _uiState.update { it.copy(isSearchingCustomers = false) }
            }
        }
    }

    fun createPlannedVisit(
        customerId: String,
        plannedDate: String,
        priority: String = "MEDIUM",
        visitType: String = "PLANNED",
        notes: String? = null,
        onResult: (Boolean, String?) -> Unit = { _, _ -> }
    ) {
        viewModelScope.launch {
            _uiState.update { it.copy(isSaving = true) }
            val request = PlannedVisitCreateRequest(
                customerId = customerId,
                plannedDate = plannedDate,
                priority = priority,
                visitType = visitType,
                notes = notes?.trim()?.ifBlank { null }
            )
            val res = planningRepository.createPlannedVisit(request)
            _uiState.update { it.copy(isSaving = false) }
            when (res) {
                is Resource.Success -> {
                    _uiState.update { it.copy(successMessage = "Visit planned successfully for ${res.data.customerName ?: "Customer"}") }
                    loadMonthlyPlan()
                    onResult(true, null)
                }
                is Resource.Error -> {
                    _uiState.update { it.copy(errorMessage = res.message) }
                    onResult(false, res.message)
                }
                is Resource.Loading -> {}
            }
        }
    }

    fun updatePlannedVisit(
        visitId: String,
        priority: String? = null,
        visitType: String? = null,
        notes: String? = null,
        onResult: (Boolean, String?) -> Unit = { _, _ -> }
    ) {
        viewModelScope.launch {
            _uiState.update { it.copy(isSaving = true) }
            val request = PlannedVisitUpdateRequest(
                priority = priority,
                notes = notes,
                visitType = visitType
            )
            val res = planningRepository.updatePlannedVisit(visitId, request)
            _uiState.update { it.copy(isSaving = false) }
            when (res) {
                is Resource.Success -> {
                    _uiState.update { it.copy(successMessage = "Planned visit updated") }
                    loadMonthlyPlan()
                    onResult(true, null)
                }
                is Resource.Error -> {
                    _uiState.update { it.copy(errorMessage = res.message) }
                    onResult(false, res.message)
                }
                is Resource.Loading -> {}
            }
        }
    }

    fun reschedulePlannedVisit(
        visitId: String,
        newDate: String,
        onResult: (Boolean, String?) -> Unit = { _, _ -> }
    ) {
        viewModelScope.launch {
            _uiState.update { it.copy(isSaving = true) }
            val res = planningRepository.reschedulePlannedVisit(visitId, newDate)
            _uiState.update { it.copy(isSaving = false) }
            when (res) {
                is Resource.Success -> {
                    _uiState.update { it.copy(successMessage = "Visit rescheduled to $newDate") }
                    loadMonthlyPlan()
                    onResult(true, null)
                }
                is Resource.Error -> {
                    _uiState.update { it.copy(errorMessage = res.message) }
                    onResult(false, res.message)
                }
                is Resource.Loading -> {}
            }
        }
    }

    fun cancelPlannedVisit(
        visitId: String,
        onResult: (Boolean, String?) -> Unit = { _, _ -> }
    ) {
        viewModelScope.launch {
            _uiState.update { it.copy(isSaving = true) }
            val res = planningRepository.deletePlannedVisit(visitId)
            _uiState.update { it.copy(isSaving = false) }
            when (res) {
                is Resource.Success -> {
                    _uiState.update { it.copy(successMessage = "Planned visit cancelled") }
                    loadMonthlyPlan()
                    onResult(true, null)
                }
                is Resource.Error -> {
                    _uiState.update { it.copy(errorMessage = res.message) }
                    onResult(false, res.message)
                }
                is Resource.Loading -> {}
            }
        }
    }

    fun resetState() {
        _uiState.value = MonthlyPlanUiState()
    }
}
