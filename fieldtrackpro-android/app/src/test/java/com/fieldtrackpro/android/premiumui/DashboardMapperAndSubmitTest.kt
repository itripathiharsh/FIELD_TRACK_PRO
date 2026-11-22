package com.fieldtrackpro.android.premiumui

import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.data.model.CustomerProspectCreate
import com.fieldtrackpro.android.data.model.DailyFieldActivitySummaryDto
import com.fieldtrackpro.android.data.model.EmployeeWorkdayResponseDto
import com.fieldtrackpro.android.data.model.VisitDto
import com.fieldtrackpro.android.data.model.WorkSessionDto
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.ui.screens.customers.AddCustomerSubmitState
import com.fieldtrackpro.android.ui.screens.customers.AddCustomerSubmitViewModel
import com.fieldtrackpro.android.ui.screens.dashboard.BeatUi
import com.fieldtrackpro.android.ui.screens.dashboard.DashboardUiMapper
import com.fieldtrackpro.android.ui.screens.dashboard.WorkdayStatus
import com.fieldtrackpro.android.ui.viewmodel.VisitsState
import com.google.gson.Gson
import kotlinx.coroutines.CompletableDeferred
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
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class DashboardUiMapperTest {
    private fun workday(status: String?, total: Double = 0.0, verified: Double = 0.0) = EmployeeWorkdayResponseDto(
        employeeId = "e1",
        workDate = "2026-11-22",
        session = status?.let { WorkSessionDto(id = "s", employeeId = "e1", workDate = "2026-11-22", status = it, startTime = "2026-11-22T03:30:00Z") },
        summary = DailyFieldActivitySummaryDto(
            workDate = "2026-11-22", totalVisits = 6, plannedVisits = 5, adhocVisits = 1, completedVisits = 2,
            collectionsTotalAmount = total, collectionsVerifiedAmount = verified
        )
    )

    private fun build(workday: EmployeeWorkdayResponseDto?, loaded: Boolean = true, visits: VisitsState = VisitsState.Success(emptyList())) =
        DashboardUiMapper.build("Good morning", "Neeraj", "Sun, 22 Nov", workday, loaded, false, false, false, null, visits, 0)

    @Test fun workdayStatusMapping() {
        assertEquals(WorkdayStatus.NOT_STARTED, build(workday(null)).workdayStatus)
        assertEquals(WorkdayStatus.STARTED, build(workday("STARTED")).workdayStatus)
        assertEquals(WorkdayStatus.COMPLETED, build(workday("COMPLETED")).workdayStatus)
        // Not loaded yet / failed to load: unknown, not "not started".
        assertEquals(WorkdayStatus.UNKNOWN, build(null, loaded = false).workdayStatus)
    }

    @Test fun notVerifiedIsTotalMinusVerifiedAndNeverNegative() {
        val ui = build(workday("STARTED", total = 12500.50, verified = 2500.0))
        assertEquals(10000.50, ui.notVerified, 0.001)
        assertEquals(0.0, build(workday("STARTED", total = 100.0, verified = 150.0)).notVerified, 0.0)
    }

    @Test fun kpisPreferServerSummary() {
        val ui = build(workday("STARTED"))
        assertEquals(2, ui.visitsDone)
        assertEquals(6, ui.visitsTotal)
        assertEquals(1, ui.adhocVisits)
    }

    @Test fun beatStaysAvailableAsStateNotAsAWholeScreen() {
        // The old screen hid every quick action unless the visit list loaded; the model now carries the
        // beat state separately so loading/errors only affect the beat section.
        assertTrue(build(workday(null), visits = VisitsState.Loading).beat is BeatUi.Loading)
        assertEquals(BeatUi.Error("offline"), build(workday(null), visits = VisitsState.Error("offline")).beat)
        val v = VisitDto(id = "1", customerId = "c", employeeId = "e", scheduledAt = "2026-11-22T09:00:00Z", status = "PENDING")
        val adhoc = v.copy(id = "2", visitType = "AD_HOC")
        val loaded = build(workday(null), visits = VisitsState.Success(listOf(v, adhoc))).beat as BeatUi.Loaded
        assertEquals(1, loaded.plannedTotal) // ad-hoc visits are not beat visits
    }

    @Test fun greeting() {
        assertEquals("Good morning", DashboardUiMapper.greetingFor(8))
        assertEquals("Good afternoon", DashboardUiMapper.greetingFor(13))
        assertEquals("Good evening", DashboardUiMapper.greetingFor(20))
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class AddCustomerSubmitViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    @Before fun setUp() = Dispatchers.setMain(dispatcher)
    @After fun tearDown() = Dispatchers.resetMain()

    private val payload = CustomerProspectCreate(name = "Shree Traders", contactNumber = "9000000000")
    private val customer: CustomerDto = Gson().fromJson("""{"id":"c1","name":"Shree Traders"}""", CustomerDto::class.java)

    @Test fun secondSubmitWhileInFlightIsIgnored() = runTest(dispatcher) {
        var calls = 0
        val gate = CompletableDeferred<Resource<CustomerDto>>()
        val vm = AddCustomerSubmitViewModel { calls++; gate.await() }

        assertTrue(vm.submit(payload))
        advanceUntilIdle()
        assertFalse(vm.submit(payload)) // double tap / re-enabled button after rotation
        assertTrue(vm.state.value is AddCustomerSubmitState.Submitting)

        gate.complete(Resource.Success(customer))
        advanceUntilIdle()
        assertEquals(1, calls)
        assertEquals(AddCustomerSubmitState.Created(customer), vm.state.value)
    }

    @Test fun failureCarriesCodesAndAcknowledgeResets() = runTest(dispatcher) {
        val vm = AddCustomerSubmitViewModel { Resource.Error("Duplicate outlet", code = 409) }
        vm.submit(payload)
        advanceUntilIdle()
        assertEquals(AddCustomerSubmitState.Failed("Duplicate outlet", 409, null), vm.state.value)
        vm.acknowledge()
        assertTrue(vm.state.value is AddCustomerSubmitState.Idle)
    }
}
