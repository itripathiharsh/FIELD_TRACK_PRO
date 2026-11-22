package com.fieldtrackpro.android.performance

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.AccountSummaryDto
import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.data.model.EmployeeMonthlyAnalyticsDto
import com.fieldtrackpro.android.data.model.EmployeeWorkdayResponseDto
import com.fieldtrackpro.android.data.model.InvoiceDto
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.CustomerRepository
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.performance.EmployeeDashboardCalculator.CollectionSummary
import com.fieldtrackpro.android.performance.EmployeeDashboardCalculator.DayActivity
import com.fieldtrackpro.android.performance.EmployeeDashboardCalculator.FieldPerformance
import com.fieldtrackpro.android.performance.EmployeeDashboardCalculator.OutletRow
import com.fieldtrackpro.android.performance.EmployeeDashboardCalculator.PortfolioSummary
import com.fieldtrackpro.android.search.CustomerPortfolioCache
import com.fieldtrackpro.android.search.CustomerSources
import com.fieldtrackpro.android.utils.Roles
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import java.time.LocalDate

sealed class Section<out T> {
    object Loading : Section<Nothing>()
    data class Progress(val done: Int, val total: Int) : Section<Nothing>()
    data class Ready<T>(val value: T) : Section<T>()
    data class Failed(val message: String) : Section<Nothing>()
}

data class PortfolioData(val rows: List<OutletRow>, val summary: PortfolioSummary)

data class EmployeeDashboardState(
    val month: LocalDate = LocalDate.now().withDayOfMonth(1),
    val notForThisRole: Boolean = false,
    val collections: Section<CollectionSummary> = Section.Loading,
    val performance: Section<FieldPerformance> = Section.Loading,
    val portfolio: Section<PortfolioData> = Section.Loading
)

/** Data access for the dashboard - existing endpoints only (no backend change). */
interface EmployeeDashboardSource {
    suspend fun portfolio(): Resource<List<CustomerDto>>
    suspend fun workday(date: LocalDate): Resource<EmployeeWorkdayResponseDto>
    suspend fun analytics(year: Int, month: Int): Resource<EmployeeMonthlyAnalyticsDto>
    suspend fun account(customerId: String): Resource<AccountSummaryDto>
    suspend fun invoices(customerId: String): Resource<List<InvoiceDto>>
}

class ApiEmployeeDashboardSource(private val tokenManager: TokenManager) : EmployeeDashboardSource {
    private val customers = CustomerRepository(ApiClient.createCustomerApi(tokenManager))
    private val workdayApi = ApiClient.createWorkdayApi(tokenManager)
    private val planningApi = ApiClient.createVisitPlanningApi(tokenManager)
    private val collectionApi = ApiClient.createCollectionApi(tokenManager)

    private suspend fun <T> call(block: suspend () -> retrofit2.Response<T>): Resource<T> = try {
        val r = block()
        val body = r.body()
        if (r.isSuccessful && body != null) Resource.Success(body)
        else Resource.Error(com.fieldtrackpro.android.data.remote.HttpErrors.message(r.code(), "Request failed (${r.code()})"), r.code())
    } catch (e: CancellationException) {
        throw e
    } catch (e: Exception) {
        Resource.Error("Can't reach the server")
    }

    override suspend fun portfolio() =
        CustomerPortfolioCache.get(tokenManager.getUserId()) { CustomerSources.loadPortfolio(customers) }
    override suspend fun workday(date: LocalDate) = call { workdayApi.getTodayWorkday(date.toString()) }
    override suspend fun analytics(year: Int, month: Int) = call { planningApi.getMyMonthAnalytics(year, month) }
    override suspend fun account(customerId: String) = call { collectionApi.getAccountSummary(customerId) }
    override suspend fun invoices(customerId: String) = call { collectionApi.getCustomerInvoices(customerId) }
}

class EmployeeDashboardViewModel(
    private val source: EmployeeDashboardSource,
    private val role: () -> String?,
    private val today: () -> LocalDate = { LocalDate.now() },
    private val parallelism: Int = 4
) : ViewModel() {

    private val _state = MutableStateFlow(EmployeeDashboardState())
    val state: StateFlow<EmployeeDashboardState> = _state.asStateFlow()
    private var job: Job? = null
    private var loadedOnce = false

    fun onOpened() {
        if (!loadedOnce) refresh()
    }

    fun refresh() {
        // Access control: this dashboard shows the CALLER's own data via employee-scoped endpoints. Admin and
        // accountant accounts have no personal field activity here; they keep using the web reports (existing RBAC).
        // Only an explicit EMPLOYEE role (Roles.displayRole maps unknown roles such as ACCOUNTANT to EMPLOYEE for
        // privilege safety, so it cannot be used here).
        if (role()?.trim()?.uppercase() != Roles.EMPLOYEE) {
            _state.value = EmployeeDashboardState(notForThisRole = true)
            return
        }
        loadedOnce = true
        job?.cancel()
        val now = today()
        _state.value = EmployeeDashboardState(month = now.withDayOfMonth(1))
        job = viewModelScope.launch {
            launch { loadActivity(now) }
            launch { loadPortfolio(now) }
        }
    }

    private suspend fun loadActivity(now: LocalDate) = coroutineScope {
        val gate = Semaphore(parallelism)
        val dates = (1..now.dayOfMonth).map { now.withDayOfMonth(it) }
        val analyticsDeferred = async { source.analytics(now.year, now.monthValue) }
        val results = dates.map { d -> async { gate.withPermit { d to source.workday(d) } } }.awaitAll()
        val days: List<DayActivity> = results.mapNotNull { (d, r) -> (r as? Resource.Success)?.let { EmployeeDashboardCalculator.dayActivity(d, it.data) } }
        val firstError = results.firstNotNullOfOrNull { (_, r) -> (r as? Resource.Error)?.message }
        _state.update {
            it.copy(collections = if (days.isEmpty() && firstError != null) Section.Failed(firstError)
            else Section.Ready(EmployeeDashboardCalculator.collections(days, now, dates.size)))
        }
        val analytics = (analyticsDeferred.await() as? Resource.Success)?.data
        _state.update { it.copy(performance = Section.Ready(EmployeeDashboardCalculator.performance(analytics, days))) }
    }

    private suspend fun loadPortfolio(now: LocalDate) = coroutineScope {
        val customers = when (val p = source.portfolio()) {
            is Resource.Success -> p.data
            is Resource.Error -> {
                _state.update { it.copy(portfolio = Section.Failed(p.message)) }
                return@coroutineScope
            }
            else -> emptyList()
        }
        val gate = Semaphore(parallelism)
        var done = 0
        _state.update { it.copy(portfolio = Section.Progress(0, customers.size)) }
        val rows = customers.map { c ->
            async {
                gate.withPermit {
                    val acc = source.account(c.id)
                    val account = (acc as? Resource.Success)?.data
                    val outstanding = account?.let { com.fieldtrackpro.android.utils.MoneyFormat.parse(it.totalOutstanding) }
                    // Bills are only needed for outlets that owe something (keeps the request count down).
                    val invoices = if (outstanding != null && outstanding.signum() > 0) (source.invoices(c.id) as? Resource.Success)?.data else emptyList()
                    val row = EmployeeDashboardCalculator.outletRow(c, account, invoices, now, (acc as? Resource.Error)?.message)
                    synchronized(this@EmployeeDashboardViewModel) { done++ }
                    _state.update { it.copy(portfolio = Section.Progress(done, customers.size)) }
                    row
                }
            }
        }.awaitAll()
        _state.update { it.copy(portfolio = Section.Ready(PortfolioData(rows, EmployeeDashboardCalculator.portfolio(rows)))) }
    }

    fun reset() {
        job?.cancel()
        loadedOnce = false
        _state.value = EmployeeDashboardState()
    }
}
