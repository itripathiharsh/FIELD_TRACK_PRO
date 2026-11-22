package com.fieldtrackpro.android.phase3

import com.fieldtrackpro.android.data.api.VisitPlanningApi
import com.fieldtrackpro.android.data.model.EmployeeMonthlyAnalyticsDto
import com.fieldtrackpro.android.data.model.MonthlyVisitPlanDto
import com.fieldtrackpro.android.data.model.PlannedVisitDto
import com.fieldtrackpro.android.data.repository.CustomerRepository
import com.fieldtrackpro.android.data.repository.VisitPlanningRepository
import com.fieldtrackpro.android.search.CustomerPortfolioCache
import com.fieldtrackpro.android.ui.viewmodel.MonthlyPlanningViewModel
import com.fieldtrackpro.android.ui.viewmodel.PlanLoadError
import com.fieldtrackpro.android.ui.viewmodel.summarize
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.Response

@OptIn(ExperimentalCoroutinesApi::class)
class MonthlyPlanViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    private val planCalls = mutableListOf<String>()
    private var planCode: Int? = null // null = success
    private var signedIn = true
    private var userId = "u1"

    private fun visit(id: String, date: String, status: String) =
        PlannedVisitDto(id = id, monthlyPlanId = "p", employeeId = "e", customerId = "c$id", plannedDate = date, status = status, customerName = "Outlet $id")

    private val planningApi: VisitPlanningApi = stub { name, args ->
        when (name) {
            "getMyPlan" -> {
                val y = args!![0] as Int; val m = args[1] as Int
                planCalls += "$y-$m"
                planCode?.let { return@stub httpError<MonthlyVisitPlanDto>(it) }
                Response.success(MonthlyVisitPlanDto(id = "p", employeeId = "e", year = y, month = m,
                    plannedVisits = listOf(visit("1", "%04d-%02d-03".format(y, m), "COMPLETED"), visit("2", "%04d-%02d-04".format(y, m), "PLANNED"), visit("3", "%04d-%02d-04".format(y, m), "CANCELLED"))))
            }
            "getMyMonthAnalytics" -> planCode?.let { httpError<EmployeeMonthlyAnalyticsDto>(it) }
                ?: Response.success(EmployeeMonthlyAnalyticsDto(employeeId = "e", employeeName = "E", year = args!![0] as Int, month = args[1] as Int, totalPlanned = 2, completed = 1))
            else -> throw IllegalStateException(name)
        }
    }

    private fun vm() = MonthlyPlanningViewModel(
        tokenManager = null,
        customPlanningRepository = VisitPlanningRepository(planningApi),
        customCustomerRepository = CustomerRepository(FakeCustomerApi(listOf(cust("c1", "Sharma Traders"))).api),
        currentUserId = { userId },
        isSignedIn = { signedIn }
    )

    @Before fun setUp() { Dispatchers.setMain(dispatcher); CustomerPortfolioCache.clear() }
    @After fun tearDown() = Dispatchers.resetMain()

    @Test fun constructingTheViewModelMakesNoRequest() = runTest(dispatcher) {
        // It is created on the login screen; any request there has no token and comes back 401.
        vm()
        advanceUntilIdle()
        assertTrue(planCalls.isEmpty())
    }

    @Test fun openingWhileSignedOutShowsSessionStateNotZeros() = runTest(dispatcher) {
        signedIn = false
        val v = vm()
        v.onScreenOpened(); advanceUntilIdle()
        assertTrue(planCalls.isEmpty())
        assertEquals(PlanLoadError.UNAUTHORIZED, v.uiState.value.loadError)
        assertFalse(v.uiState.value.hasLoadedPlan)
    }

    @Test fun signedInOpenLoadsThePlanAndCounts() = runTest(dispatcher) {
        val v = vm()
        v.onScreenOpened(); advanceUntilIdle()
        val s = v.uiState.value
        assertTrue(s.hasLoadedPlan)
        val sum = summarize(s.plan!!, s.analytics)
        assertEquals(2, sum.planned)       // cancelled excluded
        assertEquals(1, sum.completed)
        assertEquals(1, sum.remaining)
        assertEquals(50, sum.completionPercent)
        assertEquals(1, planCalls.size)
        v.onScreenOpened(); advanceUntilIdle()
        assertEquals(1, planCalls.size)    // already loaded: no duplicate request
    }

    @Test fun http401IsReportedAndNoMetricsAreShown() = runTest(dispatcher) {
        planCode = 401
        val v = vm()
        v.onScreenOpened(); advanceUntilIdle()
        val s = v.uiState.value
        assertEquals(PlanLoadError.UNAUTHORIZED, s.loadError)
        assertNull(s.plan)
        assertFalse(s.hasLoadedPlan)
    }

    @Test fun networkAndServerErrorsAreDistinguished() = runTest(dispatcher) {
        planCode = 500
        val v = vm()
        v.onScreenOpened(); advanceUntilIdle()
        assertEquals(PlanLoadError.SERVER, v.uiState.value.loadError)
        assertEquals(PlanLoadError.NETWORK, v.classify(null))
        assertEquals(PlanLoadError.FORBIDDEN, v.classify(403))
    }

    @Test fun aFailedMonthNeverShowsThePreviousMonthsNumbers() = runTest(dispatcher) {
        val v = vm()
        v.onScreenOpened(); advanceUntilIdle()
        planCode = 503
        v.nextMonth(); advanceUntilIdle()
        assertNull(v.uiState.value.plan)
        assertFalse(v.uiState.value.hasLoadedPlan)
    }

    @Test fun anotherUserNeverSeesThePreviousPlan() = runTest(dispatcher) {
        val v = vm()
        v.onScreenOpened(); advanceUntilIdle()
        userId = "u2"
        v.onScreenOpened(); advanceUntilIdle()
        assertEquals("u2", v.uiState.value.loadedForUserId)
        assertEquals(2, planCalls.size)
    }

    @Test fun duplicateAddIsIgnoredWhileSaving() = runTest(dispatcher) {
        var creates = 0
        val api: VisitPlanningApi = stub { name, _ ->
            if (name == "createPlannedVisit") { creates++; httpError<PlannedVisitDto>(400) } else throw IllegalStateException(name)
        }
        val v = MonthlyPlanningViewModel(null, VisitPlanningRepository(api), CustomerRepository(FakeCustomerApi(emptyList()).api), { "u1" }, { true })
        v.createPlannedVisit("c1", "2099-01-02")
        v.createPlannedVisit("c1", "2099-01-02")
        advanceUntilIdle()
        assertEquals(1, creates)
        assertTrue(v.uiState.value.errorMessage != null) // action error, not a load error
        assertNull(v.uiState.value.loadError)
    }
}
