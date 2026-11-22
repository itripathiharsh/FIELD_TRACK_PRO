package com.fieldtrackpro.android.premiumui

import com.fieldtrackpro.android.data.api.CustomerApi
import com.fieldtrackpro.android.data.api.GeoApi
import com.fieldtrackpro.android.data.api.VisitApi
import com.fieldtrackpro.android.data.local.InMemorySharedPreferences
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.VisitDto
import com.fieldtrackpro.android.data.repository.VisitRepository
import com.fieldtrackpro.android.ui.viewmodel.VisitTab
import com.fieldtrackpro.android.ui.viewmodel.VisitsState
import com.fieldtrackpro.android.ui.viewmodel.VisitsViewModel
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
import java.lang.reflect.Proxy

@OptIn(ExperimentalCoroutinesApi::class)
class DashboardIsolationTest {
    private val dispatcher = StandardTestDispatcher()

    /** "today|status|search" or "all|status|search" for every list request. */
    private val requests = mutableListOf<String>()

    private fun visit(id: String, type: String = "PLANNED") =
        VisitDto(id = id, customerId = "c-$id", employeeId = "e1", scheduledAt = "2026-11-22T09:00:00Z", status = "PENDING", visitType = type)

    private inline fun <reified T> stub(crossinline handler: (String, Array<out Any?>?) -> Any?): T =
        Proxy.newProxyInstance(T::class.java.classLoader, arrayOf(T::class.java)) { _, m, args ->
            when (m.name) {
                "toString" -> "stub"
                "hashCode" -> 1
                "equals" -> false
                else -> handler(m.name, args)
            }
        } as T

    private fun viewModel(): VisitsViewModel {
        val visitApi = stub<VisitApi> { name, args ->
            when (name) {
                "getMyTodayVisits" -> {
                    requests += "today|${args!![0]}|${args[1]}"
                    Response.success(listOf(visit("t1"), visit("t2", "AD_HOC")))
                }
                "getVisits" -> {
                    requests += "all|${args!![0]}|${args[1]}"
                    Response.success(listOf(visit("old1")))
                }
                else -> throw IllegalStateException("unexpected $name")
            }
        }
        val queue = OfflineQueueManager(InMemorySharedPreferences())
        val repo = VisitRepository(
            visitApi = visitApi,
            customerApi = stub<CustomerApi> { n, _ -> throw IllegalStateException(n) },
            geoApi = stub<GeoApi> { n, _ -> throw IllegalStateException(n) },
            offlineQueueManager = queue
        )
        return VisitsViewModel(TokenManager(null, InMemorySharedPreferences()), queue, repositoryOverride = repo)
    }

    @Before fun setUp() = Dispatchers.setMain(dispatcher)
    @After fun tearDown() = Dispatchers.resetMain()

    @Test fun dashboardBeatIgnoresTheVisitsScreenFilters() = runTest(dispatcher) {
        val vm = viewModel()
        // The user leaves the visits screen on "All", filtered to COMPLETED, searching "sharma".
        vm.setTab(VisitTab.ALL)
        vm.setStatusFilter("COMPLETED")
        vm.setSearchQuery("sharma")
        advanceUntilIdle()
        requests.clear()

        vm.loadDashboardVisits()
        advanceUntilIdle()

        assertEquals(listOf("today|null|null"), requests)
        val beat = vm.dashboardVisitsState.value as VisitsState.Success
        assertEquals(listOf("t1", "t2"), beat.visits.map { it.id })
        // ...and the visits screen keeps its own state.
        assertFalse((vm.visitsState.value as VisitsState.Success).isTodayTab)
    }

    @Test fun switchingTabDuringALoadShowsTheNewTab() = runTest(dispatcher) {
        val vm = viewModel()
        vm.loadVisits()          // TODAY page queued (in flight)
        vm.setTab(VisitTab.ALL)  // used to be dropped by the "a page is loading" guard
        advanceUntilIdle()

        assertEquals("all|null|null", requests.last())
        val state = vm.visitsState.value as VisitsState.Success
        assertFalse(state.isTodayTab)
        assertEquals(listOf("old1"), state.visits.map { it.id })
    }

    @Test fun clearStateResetsTheDashboardBeat() = runTest(dispatcher) {
        val vm = viewModel()
        vm.loadDashboardVisits()
        advanceUntilIdle()
        vm.clearState()
        assertTrue(vm.dashboardVisitsState.value is VisitsState.Loading)
        assertNull(vm.customerSearchError.value)
    }
}
