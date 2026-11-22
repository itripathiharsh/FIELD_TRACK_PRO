package com.fieldtrackpro.android.performance

import com.fieldtrackpro.android.data.model.AccountSummaryDto
import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.data.model.EmployeeMonthlyAnalyticsDto
import com.fieldtrackpro.android.data.model.EmployeeWorkdayResponseDto
import com.fieldtrackpro.android.data.model.InvoiceDto
import com.fieldtrackpro.android.utils.MoneyFormat
import java.math.BigDecimal
import java.time.LocalDate
import java.time.temporal.ChronoUnit

/**
 * Employee dashboard calculations. Every figure has ONE documented source (see design-review/EMPLOYEE_DASHBOARD.md):
 *
 *  COLLECTIONS (money this employee collected) come ONLY from the employee's own daily workday summary
 *  (GET /workday/today?work_date=), which the server computes from payments WHERE employee_id = this employee.
 *  Tally receipts have no employee_id, so they are never counted here; a Tally receipt linked to a field
 *  collection is the same money and is already represented by that field collection.
 *
 *  OUTSTANDING (money customers owe) comes from each outlet's account (GET /customers/{id}/account) and bills
 *  (GET /customers/{id}/invoices). It is CUSTOMER-level data for the employee's CURRENT portfolio - not money the
 *  employee collected, and not historical ownership. The two are never added together.
 *
 *  FIELD PERFORMANCE comes from the monthly plan analytics (visits by visit.employee_id) and the workday summaries.
 */
object EmployeeDashboardCalculator {

    // ------------------------------------------------------------------------------------------- collections
    data class DayActivity(
        val date: LocalDate,
        val worked: Boolean,
        val totalVisits: Int,
        val completedVisits: Int,
        val collectedTotal: BigDecimal,
        val collectedVerified: BigDecimal
    )

    fun dayActivity(date: LocalDate, w: EmployeeWorkdayResponseDto): DayActivity {
        val s = w.summary
        val status = w.session?.status?.uppercase()
        return DayActivity(
            date = date,
            worked = status == "STARTED" || status == "COMPLETED",
            totalVisits = s.totalVisits,
            completedVisits = s.completedVisits,
            collectedTotal = BigDecimal.valueOf(s.collectionsTotalAmount),
            collectedVerified = BigDecimal.valueOf(s.collectionsVerifiedAmount)
        )
    }

    data class CollectionSummary(
        val todayVerified: BigDecimal,
        val todayRecorded: BigDecimal,
        val monthVerified: BigDecimal,
        val monthRecorded: BigDecimal,
        /** Recorded but not verified (pending or rejected - the summary API does not split them). */
        val monthNotVerified: BigDecimal,
        val daysWithCollections: Int,
        /** Daily verified amounts for the trend chart, oldest first. */
        val dailyVerified: List<Pair<LocalDate, BigDecimal>>,
        /** Days of the month whose summary could not be loaded: totals are then marked incomplete. */
        val missingDays: Int
    ) {
        val isComplete: Boolean get() = missingDays == 0
    }

    fun collections(days: List<DayActivity>, today: LocalDate, expectedDays: Int): CollectionSummary {
        val sorted = days.sortedBy { it.date }
        val t = sorted.firstOrNull { it.date == today }
        val monthVerified = sorted.fold(BigDecimal.ZERO) { a, d -> a + d.collectedVerified }
        val monthRecorded = sorted.fold(BigDecimal.ZERO) { a, d -> a + d.collectedTotal }
        return CollectionSummary(
            todayVerified = t?.collectedVerified ?: BigDecimal.ZERO,
            todayRecorded = t?.collectedTotal ?: BigDecimal.ZERO,
            monthVerified = monthVerified,
            monthRecorded = monthRecorded,
            monthNotVerified = (monthRecorded - monthVerified).max(BigDecimal.ZERO),
            daysWithCollections = sorted.count { it.collectedTotal.signum() > 0 },
            dailyVerified = sorted.map { it.date to it.collectedVerified },
            missingDays = (expectedDays - sorted.size).coerceAtLeast(0)
        )
    }

    // --------------------------------------------------------------------------------------- performance
    data class FieldPerformance(
        val planned: Int?,
        val completed: Int?,
        val completionRatePercent: Int?,
        val missed: Int?,
        val extraUnplanned: Int?,
        val workdays: Int,
        val visitsRecorded: Int,
        val visitsCompleted: Int
    )

    fun performance(analytics: EmployeeMonthlyAnalyticsDto?, days: List<DayActivity>): FieldPerformance {
        val rate = analytics?.let {
            it.completionRate?.let { r -> Math.round(if (r <= 1.0) r * 100 else r).toInt() }
                ?: if (it.totalPlanned > 0) Math.round(it.completed * 100.0 / it.totalPlanned).toInt() else null
        }
        return FieldPerformance(
            planned = analytics?.totalPlanned,
            completed = analytics?.completed,
            completionRatePercent = rate,
            missed = analytics?.missed,
            extraUnplanned = analytics?.extraUnplanned,
            workdays = days.count { it.worked },
            visitsRecorded = days.sumOf { it.totalVisits },
            visitsCompleted = days.sumOf { it.completedVisits }
        )
    }

    // ------------------------------------------------------------------------------------------- ageing
    enum class AgeBucket(val label: String) {
        NOT_DUE("Not yet due"),
        D1_30("1–30 days past due"),
        D31_60("31–60 days past due"),
        D61_90("61–90 days past due"),
        D90_PLUS("Over 90 days past due"),
        NO_DUE_DATE("No due date on bill")
    }

    /** Due-date ageing of open bills: days past due = today - due_date (bills with nothing remaining are skipped). */
    fun bucketFor(dueDate: LocalDate?, today: LocalDate): AgeBucket {
        if (dueDate == null) return AgeBucket.NO_DUE_DATE
        val pastDue = ChronoUnit.DAYS.between(dueDate, today)
        return when {
            pastDue <= 0 -> AgeBucket.NOT_DUE
            pastDue <= 30 -> AgeBucket.D1_30
            pastDue <= 60 -> AgeBucket.D31_60
            pastDue <= 90 -> AgeBucket.D61_90
            else -> AgeBucket.D90_PLUS
        }
    }

    fun parseDate(iso: String?): LocalDate? = try {
        iso?.takeIf { it.length >= 10 }?.let { LocalDate.parse(it.substring(0, 10)) }
    } catch (e: Exception) {
        null
    }

    fun ageing(invoices: List<InvoiceDto>, today: LocalDate): Map<AgeBucket, BigDecimal> {
        val out = AgeBucket.entries.associateWith { BigDecimal.ZERO }.toMutableMap()
        for (inv in invoices) {
            val remaining = MoneyFormat.parse(inv.remainingAmount) ?: continue
            if (remaining.signum() <= 0) continue
            val b = bucketFor(parseDate(inv.dueDate), today)
            out[b] = out.getValue(b) + remaining
        }
        return out
    }

    fun pastDue(buckets: Map<AgeBucket, BigDecimal>): BigDecimal =
        listOf(AgeBucket.D1_30, AgeBucket.D31_60, AgeBucket.D61_90, AgeBucket.D90_PLUS)
            .fold(BigDecimal.ZERO) { a, b -> a + (buckets[b] ?: BigDecimal.ZERO) }

    // ---------------------------------------------------------------------------------------- portfolio
    data class OutletRow(
        val customer: CustomerDto,
        val outstanding: BigDecimal?,
        val overdue: BigDecimal?,
        val lastVisitDate: LocalDate?,
        val lastPaymentDate: LocalDate?,
        val lastPaymentAmount: BigDecimal?,
        val ageing: Map<AgeBucket, BigDecimal>?,
        /** Set when this outlet's account could not be loaded (it is then excluded from totals, and counted). */
        val unavailableReason: String? = null
    )

    fun outletRow(customer: CustomerDto, account: AccountSummaryDto?, invoices: List<InvoiceDto>?, today: LocalDate, error: String? = null): OutletRow =
        OutletRow(
            customer = customer,
            outstanding = account?.let { MoneyFormat.parse(it.totalOutstanding) },
            overdue = account?.let { MoneyFormat.parse(it.overdueAmount) },
            lastVisitDate = parseDate(account?.mostRecentVisitDate),
            lastPaymentDate = parseDate(account?.mostRecentPayment?.paymentDate),
            lastPaymentAmount = account?.mostRecentPayment?.amount?.let { MoneyFormat.parse(it) },
            ageing = invoices?.let { ageing(it, today) },
            unavailableReason = if (account == null) (error ?: "Account not available") else null
        )

    data class PortfolioSummary(
        val outlets: Int,
        val outletsWithBalance: Int,
        val totalOutstanding: BigDecimal,
        val pastDue: BigDecimal,
        val ageing: Map<AgeBucket, BigDecimal>,
        /** Outlets whose figures could not be loaded; totals exclude them and the UI says so. */
        val unavailable: Int
    )

    fun portfolio(rows: List<OutletRow>): PortfolioSummary {
        val ok = rows.filter { it.unavailableReason == null }
        val ageing = AgeBucket.entries.associateWith { b -> ok.fold(BigDecimal.ZERO) { a, r -> a + (r.ageing?.get(b) ?: BigDecimal.ZERO) } }
        return PortfolioSummary(
            outlets = rows.size,
            outletsWithBalance = ok.count { (it.outstanding ?: BigDecimal.ZERO).signum() > 0 },
            totalOutstanding = ok.fold(BigDecimal.ZERO) { a, r -> a + (r.outstanding ?: BigDecimal.ZERO) },
            pastDue = pastDue(ageing),
            ageing = ageing,
            unavailable = rows.size - ok.size
        )
    }

    /** Outlet list filtering for the "My outlets" section: name/code search + area filter, highest balance first. */
    fun filterOutlets(rows: List<OutletRow>, query: String, area: String?): List<OutletRow> {
        val q = query.trim().lowercase()
        return rows.filter { r ->
            (area == null || (r.customer.areaName ?: r.customer.territoryName) == area) &&
                (q.isEmpty() || r.customer.name.lowercase().contains(q) ||
                    (r.customer.outletCode ?: r.customer.dmsCode ?: "").lowercase().contains(q))
        }.sortedWith(compareByDescending<OutletRow> { it.outstanding ?: BigDecimal.ZERO }.thenBy { it.customer.name.lowercase() })
    }
}
