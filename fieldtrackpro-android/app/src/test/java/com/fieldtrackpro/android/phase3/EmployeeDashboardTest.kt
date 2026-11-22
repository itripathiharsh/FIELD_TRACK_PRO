package com.fieldtrackpro.android.phase3

import com.fieldtrackpro.android.data.model.AccountSummaryDto
import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.data.model.DailyFieldActivitySummaryDto
import com.fieldtrackpro.android.data.model.EmployeeMonthlyAnalyticsDto
import com.fieldtrackpro.android.data.model.EmployeeWorkdayResponseDto
import com.fieldtrackpro.android.data.model.InvoiceDto
import com.fieldtrackpro.android.data.model.PaymentDto
import com.fieldtrackpro.android.data.model.WorkSessionDto
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.performance.EmployeeDashboardCalculator
import com.fieldtrackpro.android.performance.EmployeeDashboardCalculator.AgeBucket
import com.fieldtrackpro.android.performance.EmployeeDashboardSource
import com.fieldtrackpro.android.performance.EmployeeDashboardViewModel
import com.fieldtrackpro.android.performance.Section
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.math.BigDecimal
import java.time.LocalDate

internal fun invoice(id: String, due: String?, remaining: String) = InvoiceDto(
    id = id, customerId = "c", invoiceNumber = id, invoiceDate = "2026-09-01", dueDate = due, amount = remaining, source = "TALLY",
    createdAt = "2026-09-01T00:00:00Z", verifiedPaidAmount = "0", remainingAmount = remaining, daysOutstanding = 0,
    paymentStatus = "UNPAID", agingStatus = "X", misBucket = "X"
)

internal fun account(id: String, outstanding: String, overdue: String = "0", lastPayment: PaymentDto? = null) = AccountSummaryDto(
    customerId = id, customerName = id, totalInvoiced = outstanding, totalPaid = "0", totalOutstanding = outstanding,
    overdueAmount = overdue, maxDaysOutstanding = 0, collectionStatus = "X", mostRecentPayment = lastPayment, mostRecentVisitDate = "2026-11-20T10:00:00Z"
)

internal fun workday(date: LocalDate, total: Double, verified: Double, worked: Boolean) = EmployeeWorkdayResponseDto(
    employeeId = "e", workDate = date.toString(),
    session = if (worked) WorkSessionDto(id = "s", employeeId = "e", workDate = date.toString(), status = "COMPLETED") else null,
    summary = DailyFieldActivitySummaryDto(workDate = date.toString(), totalVisits = 3, completedVisits = 2, collectionsTotalAmount = total, collectionsVerifiedAmount = verified)
)

class EmployeeDashboardCalculatorTest {
    private val today = LocalDate.of(2026, 11, 22)

    @Test fun ageingUsesBillDueDates() {
        assertEquals(AgeBucket.NOT_DUE, EmployeeDashboardCalculator.bucketFor(LocalDate.of(2026, 11, 22), today))
        assertEquals(AgeBucket.NOT_DUE, EmployeeDashboardCalculator.bucketFor(LocalDate.of(2026, 12, 1), today))
        assertEquals(AgeBucket.D1_30, EmployeeDashboardCalculator.bucketFor(LocalDate.of(2026, 11, 21), today))
        assertEquals(AgeBucket.D1_30, EmployeeDashboardCalculator.bucketFor(LocalDate.of(2026, 10, 23), today))   // 30 days
        assertEquals(AgeBucket.D31_60, EmployeeDashboardCalculator.bucketFor(LocalDate.of(2026, 10, 22), today))  // 31 days
        assertEquals(AgeBucket.D61_90, EmployeeDashboardCalculator.bucketFor(LocalDate.of(2026, 8, 24), today))   // 90 days
        assertEquals(AgeBucket.D90_PLUS, EmployeeDashboardCalculator.bucketFor(LocalDate.of(2026, 8, 23), today))
        assertEquals(AgeBucket.NO_DUE_DATE, EmployeeDashboardCalculator.bucketFor(null, today))
    }

    @Test fun ageingSumsOnlyOpenBillsAndPastDueExcludesNotDue() {
        val b = EmployeeDashboardCalculator.ageing(listOf(
            invoice("a", "2026-12-10", "1000"), invoice("b", "2026-11-01", "250.50"),
            invoice("c", "2026-07-01", "400"), invoice("d", null, "75"), invoice("e", "2026-01-01", "0")
        ), today)
        assertEquals(BigDecimal("1000"), b[AgeBucket.NOT_DUE])
        assertEquals(BigDecimal("250.50"), b[AgeBucket.D1_30])
        assertEquals(BigDecimal("400"), b[AgeBucket.D90_PLUS])
        assertEquals(BigDecimal("75"), b[AgeBucket.NO_DUE_DATE])
        assertEquals(BigDecimal("650.50"), EmployeeDashboardCalculator.pastDue(b))
    }

    @Test fun collectionsSeparateVerifiedFromRecordedAndFlagMissingDays() {
        val days = listOf(
            EmployeeDashboardCalculator.dayActivity(today.minusDays(1), workday(today.minusDays(1), 5000.0, 4000.0, true)),
            EmployeeDashboardCalculator.dayActivity(today, workday(today, 1200.5, 0.0, true))
        )
        val c = EmployeeDashboardCalculator.collections(days, today, expectedDays = 22)
        assertEquals(0, c.todayVerified.compareTo(BigDecimal.ZERO))
        assertEquals(0, c.todayRecorded.compareTo(BigDecimal("1200.5")))
        assertEquals(0, c.monthVerified.compareTo(BigDecimal("4000")))
        assertEquals(0, c.monthNotVerified.compareTo(BigDecimal("2200.5")))
        assertEquals(20, c.missingDays)
        assertTrue(!c.isComplete)
    }

    @Test fun portfolioExcludesUnavailableOutletsAndCountsThem() {
        val rows = listOf(
            EmployeeDashboardCalculator.outletRow(cust("1", "A"), account("1", "1000", "200"), listOf(invoice("x", "2026-10-01", "1000")), today),
            EmployeeDashboardCalculator.outletRow(cust("2", "B"), null, null, today, "HTTP 403"),
            EmployeeDashboardCalculator.outletRow(cust("3", "C"), account("3", "0"), emptyList(), today)
        )
        val s = EmployeeDashboardCalculator.portfolio(rows)
        assertEquals(3, s.outlets)
        assertEquals(1, s.unavailable)
        assertEquals(1, s.outletsWithBalance)
        assertEquals(0, s.totalOutstanding.compareTo(BigDecimal("1000")))
        assertEquals(0, s.pastDue.compareTo(BigDecimal("1000")))
    }

    @Test fun outletFilterAndOrder() {
        val rows = listOf(
            EmployeeDashboardCalculator.outletRow(cust("1", "Alpha", "OUT-1", area = "Kidwai"), account("1", "10"), null, today),
            EmployeeDashboardCalculator.outletRow(cust("2", "Beta", "OUT-2", area = "Civil Lines"), account("2", "500"), null, today),
            EmployeeDashboardCalculator.outletRow(cust("3", "Gamma", "OUT-3", area = "Kidwai"), account("3", "50"), null, today)
        )
        assertEquals(listOf("2", "3", "1"), EmployeeDashboardCalculator.filterOutlets(rows, "", null).map { it.customer.id })
        assertEquals(listOf("3", "1"), EmployeeDashboardCalculator.filterOutlets(rows, "", "Kidwai").map { it.customer.id })
        assertEquals(listOf("2"), EmployeeDashboardCalculator.filterOutlets(rows, "out-2", null).map { it.customer.id })
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class EmployeeDashboardViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    @Before fun setUp() = Dispatchers.setMain(dispatcher)
    @After fun tearDown() = Dispatchers.resetMain()

    private val today = LocalDate.of(2026, 11, 3)

    private inner class FakeSource : EmployeeDashboardSource {
        val calls = mutableListOf<String>()
        override suspend fun portfolio(): Resource<List<CustomerDto>> { calls += "portfolio"; return Resource.Success(listOf(cust("1", "Owes"), cust("2", "Clear"))) }
        override suspend fun workday(date: LocalDate): Resource<EmployeeWorkdayResponseDto> { calls += "workday $date"; return Resource.Success(workday(date, 1000.0, 600.0, date.dayOfMonth != 2)) }
        override suspend fun analytics(year: Int, month: Int): Resource<EmployeeMonthlyAnalyticsDto> =
            Resource.Success(EmployeeMonthlyAnalyticsDto(employeeId = "e", employeeName = "E", year = year, month = month, totalPlanned = 10, completed = 4))
        override suspend fun account(customerId: String): Resource<AccountSummaryDto> {
            calls += "account $customerId"
            // A Tally receipt (no employee) as the outlet's last payment: it must never count as this employee's collection.
            val tallyReceipt = com.google.gson.Gson().fromJson("""{"id":"r","customer_id":"$customerId","amount":"99999","payment_method":"BANK","payment_date":"2026-11-01","status":"VERIFIED","created_at":"2026-11-01"}""", PaymentDto::class.java)
            return Resource.Success(account(customerId, if (customerId == "1") "5000" else "0", lastPayment = tallyReceipt))
        }
        override suspend fun invoices(customerId: String): Resource<List<InvoiceDto>> { calls += "invoices $customerId"; return Resource.Success(listOf(invoice("i", "2026-10-01", "5000"))) }
    }

    @Test fun employeeSeesOnlyEmployeeLinkedCollectionsAndCustomerLevelOutstanding() = runTest(dispatcher) {
        val src = FakeSource()
        val vm = EmployeeDashboardViewModel(src, { "EMPLOYEE" }, { today })
        vm.onOpened(); advanceUntilIdle()
        val s = vm.state.value
        val c = (s.collections as Section.Ready).value
        assertEquals(0, c.monthVerified.compareTo(BigDecimal("1800")))   // 3 days x 600, from workday summaries only
        assertEquals(0, c.monthRecorded.compareTo(BigDecimal("3000")))
        val p = (s.performance as Section.Ready).value
        assertEquals(2, p.workdays)
        assertEquals(40, p.completionRatePercent)
        val pf = (s.portfolio as Section.Ready).value
        assertEquals(0, pf.summary.totalOutstanding.compareTo(BigDecimal("5000")))
        // Bills are fetched only for the outlet that owes money.
        assertTrue("invoices 1" in src.calls && "invoices 2" !in src.calls)
    }

    @Test fun adminAndAccountantAccountsGetNoPersonalDashboard() = runTest(dispatcher) {
        for (role in listOf("ADMIN", "SUPER_ADMIN", "ACCOUNTANT")) {
            val src = FakeSource()
            val vm = EmployeeDashboardViewModel(src, { role }, { today })
            vm.onOpened(); advanceUntilIdle()
            assertTrue(vm.state.value.notForThisRole)
            assertTrue(src.calls.isEmpty())
        }
    }

    @Test fun failedPortfolioIsAnErrorNotZero() = runTest(dispatcher) {
        val src = object : EmployeeDashboardSource by FakeSource() {
            override suspend fun portfolio(): Resource<List<CustomerDto>> = Resource.Error("Can't reach the server")
        }
        val vm = EmployeeDashboardViewModel(src, { "EMPLOYEE" }, { today })
        vm.onOpened(); advanceUntilIdle()
        assertTrue(vm.state.value.portfolio is Section.Failed)
    }
}
