package com.fieldtrackpro.android.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.EmployeeMonthlyAnalyticsDto
import com.fieldtrackpro.android.data.model.MonthlyVisitPlanDto
import com.fieldtrackpro.android.data.model.PlannedVisitCreateRequest
import com.fieldtrackpro.android.data.model.PlannedVisitDto
import com.fieldtrackpro.android.data.model.PlannedVisitUpdateRequest
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.CustomerRepository
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.data.repository.VisitPlanningRepository
import com.fieldtrackpro.android.search.CustomerPortfolioCache
import com.fieldtrackpro.android.search.CustomerSearchController
import com.fieldtrackpro.android.search.CustomerSources
import kotlinx.coroutines.Job
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.util.Calendar
import java.util.Locale

/** Why the plan could not be loaded: drives a specific message and recovery action (never fake zeros). */
enum class PlanLoadError { UNAUTHORIZED, FORBIDDEN, NETWORK, SERVER }

data class MonthlyPlanUiState(
    val year: Int = Calendar.getInstance().get(Calendar.YEAR),
    val month: Int = Calendar.getInstance().get(Calendar.MONTH) + 1,
    val isLoading: Boolean = false,
    val isSaving: Boolean = false,
    val plan: MonthlyVisitPlanDto? = null,
    val analytics: EmployeeMonthlyAnalyticsDto? = null,
    val selectedFilter: String = "ALL", // ALL, PLANNED, COMPLETED
    val calendarView: Boolean = false,
    val selectedDate: String? = null,
    /** Load failure of the plan for [year]/[month]. When set, metrics are NOT shown. */
    val loadError: PlanLoadError? = null,
    val loadErrorMessage: String? = null,
    /** Failure of an action (add / edit / reschedule / cancel); the plan stays visible. */
    val errorMessage: String? = null,
    val successMessage: String? = null,
    /** User id the current plan belongs to (a different signed-in user must never see it). */
    val loadedForUserId: String? = null
) {
    val visibleVisits: List<PlannedVisitDto>
        get() = (plan?.plannedVisits ?: emptyList()).filter { it.status != "CANCELLED" }

    val filteredVisits: List<PlannedVisitDto>
        get() = visibleVisits.filter { visit ->
            when (selectedFilter) {
                "PLANNED" -> visit.status == "PLANNED"
                "COMPLETED" -> visit.status == "COMPLETED"
                else -> true
            }
        }

    /** Metrics are only meaningful when the plan for this month actually loaded. */
    val hasLoadedPlan: Boolean
        get() = plan != null && loadError == null && plan.year == year && plan.month == month
}

/** Monthly numbers derived from the loaded plan (and analytics when available). Pure; unit tested. */
data class PlanSummary(val planned: Int, val completed: Int, val remaining: Int, val activeDays: Int, val completionPercent: Int)

fun summarize(plan: MonthlyVisitPlanDto, analytics: EmployeeMonthlyAnalyticsDto?): PlanSummary {
    val visits = plan.plannedVisits.filter { it.status != "CANCELLED" }
    val planned = visits.size
    val completed = visits.count { it.status == "COMPLETED" }
    val remaining = visits.count { it.status == "PLANNED" }
    val activeDays = if (plan.activeDaysCount > 0) plan.activeDaysCount else visits.map { it.plannedDate }.distinct().size
    val pct = if (planned == 0) 0 else Math.round(completed * 100.0 / planned).toInt()
    return PlanSummary(planned, completed, remaining, activeDays, pct)
}

class MonthlyPlanningViewModel(
    private val tokenManager: TokenManager? = null,
    customPlanningRepository: VisitPlanningRepository? = null,
    customCustomerRepository: CustomerRepository? = null,
    private val currentUserId: () -> String? = { tokenManager?.getUserId() },
    private val isSignedIn: () -> Boolean = { tokenManager?.isLoggedIn() == true }
) : ViewModel() {

    private val planningRepository: VisitPlanningRepository = customPlanningRepository ?: VisitPlanningRepository(
        ApiClient.createVisitPlanningApi(tokenManager ?: throw IllegalArgumentException("TokenManager must not be null"))
    )

    private val customerRepository: CustomerRepository = customCustomerRepository ?: CustomerRepository(
        ApiClient.createCustomerApi(tokenManager ?: throw IllegalArgumentException("TokenManager must not be null"))
    )

    private val _uiState = MutableStateFlow(MonthlyPlanUiState())
    val uiState: StateFlow<MonthlyPlanUiState> = _uiState.asStateFlow()

    /** Ranked customer search shared with the Off-Beat picker (portfolio + directory, stale-safe). */
    val customerSearch = CustomerSearchController(
        scope = viewModelScope,
        currentUserId = currentUserId,
        loadPortfolio = { CustomerSources.loadPortfolio(customerRepository) },
        searchDirectory = { q -> CustomerSources.searchDirectory(customerRepository, q) }
    )

    private var loadJob: Job? = null

    // NOTE: no init{} network call. This ViewModel is created by MainActivity when the navigation graph is first
    // composed - on the splash/login screen, BEFORE sign-in. It used to load the plan and the customer list right
    // there: those requests carried no bearer token, the backend answered 401, TokenAuthenticator (correctly) does
    // not try to refresh a request that never had a session, and the screen kept "Failed to load monthly plan (401)"
    // with zero counts and an empty customer list. Loading now starts when a signed-in user opens the screen.

    /** Called every time the Monthly Plan screen is shown. */
    fun onScreenOpened() {
        if (!isSignedIn()) {
            _uiState.update {
                it.copy(plan = null, analytics = null, loadError = PlanLoadError.UNAUTHORIZED,
                    loadErrorMessage = "Your session has ended. Sign in again to see your plan.")
            }
            return
        }
        val s = _uiState.value
        if (s.loadedForUserId != null && s.loadedForUserId != currentUserId()) resetState()
        val now = _uiState.value
        if (now.loadedForUserId != currentUserId() || !now.hasLoadedPlan) loadMonthlyPlan()
        customerSearch.start()
    }

    private fun getDefaultDateForMonth(year: Int, month: Int): String {
        val todayCal = Calendar.getInstance()
        val currentYear = todayCal.get(Calendar.YEAR)
        val currentMonth = todayCal.get(Calendar.MONTH) + 1
        return if (year == currentYear && month == currentMonth) {
            String.format(Locale.US, "%04d-%02d-%02d", year, month, todayCal.get(Calendar.DAY_OF_MONTH))
        } else {
            String.format(Locale.US, "%04d-%02d-%02d", year, month, 1)
        }
    }

    fun loadMonthlyPlan(year: Int = _uiState.value.year, month: Int = _uiState.value.month) {
        loadJob?.cancel()
        _uiState.update {
            val sameMonth = it.plan?.year == year && it.plan.month == month
            it.copy(
                isLoading = true, loadError = null, loadErrorMessage = null, year = year, month = month,
                // Never show another month's plan (or its numbers) while this one loads or after it fails.
                plan = if (sameMonth) it.plan else null,
                analytics = if (sameMonth) it.analytics else null
            )
        }
        loadJob = viewModelScope.launch {
            val planDeferred = async { planningRepository.getMyPlan(year = year, month = month) }
            val analyticsDeferred = async { planningRepository.getMyMonthAnalytics(year = year, month = month) }
            val planRes = planDeferred.await()
            val analyticsRes = analyticsDeferred.await()

            when (planRes) {
                is Resource.Success -> _uiState.update {
                    it.copy(
                        isLoading = false,
                        plan = planRes.data,
                        analytics = (analyticsRes as? Resource.Success)?.data,
                        loadError = null,
                        loadErrorMessage = null,
                        loadedForUserId = currentUserId()
                    )
                }
                is Resource.Error -> {
                    val kind = classify(planRes.code)
                    _uiState.update {
                        it.copy(isLoading = false, plan = null, analytics = null, loadError = kind,
                            loadErrorMessage = messageFor(kind, planRes.message))
                    }
                }
                is Resource.Loading -> {}
            }
        }
    }

    internal fun classify(code: Int?): PlanLoadError = when (code) {
        401 -> PlanLoadError.UNAUTHORIZED
        403 -> PlanLoadError.FORBIDDEN
        null -> PlanLoadError.NETWORK
        else -> PlanLoadError.SERVER
    }

    private fun messageFor(kind: PlanLoadError, raw: String): String = when (kind) {
        PlanLoadError.UNAUTHORIZED -> "Your session has ended. Sign in again to see your plan."
        PlanLoadError.FORBIDDEN -> "Your account is not allowed to view a monthly plan. Ask your administrator."
        PlanLoadError.NETWORK -> "Can't reach the server. Check your internet connection and try again."
        PlanLoadError.SERVER -> "The plan could not be loaded ($raw). Try again."
    }

    fun refresh() {
        loadMonthlyPlan()
        customerSearch.start(force = true)
    }

    private fun goToMonth(year: Int, month: Int) {
        val defaultDate = if (_uiState.value.calendarView) getDefaultDateForMonth(year, month) else null
        _uiState.update { it.copy(year = year, month = month, selectedDate = defaultDate) }
        loadMonthlyPlan(year, month)
    }

    fun previousMonth() {
        val s = _uiState.value
        if (s.month == 1) goToMonth(s.year - 1, 12) else goToMonth(s.year, s.month - 1)
    }

    fun nextMonth() {
        val s = _uiState.value
        if (s.month == 12) goToMonth(s.year + 1, 1) else goToMonth(s.year, s.month + 1)
    }

    fun selectMonth(year: Int, month: Int) = goToMonth(year, month)

    fun setFilter(filter: String) {
        _uiState.update { it.copy(selectedFilter = filter) }
    }

    fun setCalendarView(enabled: Boolean) {
        _uiState.update { state ->
            state.copy(
                calendarView = enabled,
                selectedDate = if (enabled && state.selectedDate == null) getDefaultDateForMonth(state.year, state.month) else state.selectedDate
            )
        }
    }

    fun selectDate(date: String?) {
        _uiState.update { it.copy(selectedDate = date) }
    }

    fun clearMessages() {
        _uiState.update { it.copy(errorMessage = null, successMessage = null) }
    }

    private fun runAction(
        success: (PlannedVisitDto?) -> String,
        onResult: (Boolean, String?) -> Unit,
        block: suspend () -> Resource<*>
    ) {
        if (_uiState.value.isSaving) return // duplicate-submission guard
        _uiState.update { it.copy(isSaving = true, errorMessage = null) }
        viewModelScope.launch {
            val res = block()
            _uiState.update { it.copy(isSaving = false) }
            when (res) {
                is Resource.Success -> {
                    _uiState.update { it.copy(successMessage = success(res.data as? PlannedVisitDto)) }
                    loadMonthlyPlan()
                    onResult(true, null)
                }
                is Resource.Error -> {
                    _uiState.update { it.copy(errorMessage = res.message) }
                    onResult(false, res.message)
                }
                else -> onResult(false, null)
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
    ) = runAction({ "Visit planned for ${it?.customerName ?: "the customer"}" }, onResult) {
        planningRepository.createPlannedVisit(
            PlannedVisitCreateRequest(
                customerId = customerId,
                plannedDate = plannedDate,
                priority = priority,
                visitType = visitType,
                notes = notes?.trim()?.ifBlank { null }
            )
        )
    }

    fun updatePlannedVisit(
        visitId: String,
        priority: String? = null,
        visitType: String? = null,
        notes: String? = null,
        onResult: (Boolean, String?) -> Unit = { _, _ -> }
    ) = runAction({ "Planned visit updated" }, onResult) {
        planningRepository.updatePlannedVisit(visitId, PlannedVisitUpdateRequest(priority = priority, notes = notes, visitType = visitType))
    }

    fun reschedulePlannedVisit(
        visitId: String,
        newDate: String,
        onResult: (Boolean, String?) -> Unit = { _, _ -> }
    ) = runAction({ "Visit moved to $newDate" }, onResult) {
        planningRepository.reschedulePlannedVisit(visitId, newDate)
    }

    fun cancelPlannedVisit(
        visitId: String,
        onResult: (Boolean, String?) -> Unit = { _, _ -> }
    ) = runAction({ "Planned visit cancelled" }, onResult) {
        planningRepository.deletePlannedVisit(visitId)
    }

    fun resetState() {
        loadJob?.cancel()
        _uiState.value = MonthlyPlanUiState()
        customerSearch.clear()
        CustomerPortfolioCache.clear()
    }
}
