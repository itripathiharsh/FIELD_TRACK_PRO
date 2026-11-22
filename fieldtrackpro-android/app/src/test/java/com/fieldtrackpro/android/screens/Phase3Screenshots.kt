package com.fieldtrackpro.android.screens

import android.graphics.Bitmap
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.unit.dp
import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.data.model.EmployeeMonthlyAnalyticsDto
import com.fieldtrackpro.android.data.model.MonthlyVisitPlanDto
import com.fieldtrackpro.android.data.model.PlannedVisitDto
import com.fieldtrackpro.android.performance.EmployeeDashboardCalculator
import com.fieldtrackpro.android.performance.EmployeeDashboardContent
import com.fieldtrackpro.android.performance.EmployeeDashboardState
import com.fieldtrackpro.android.performance.PortfolioData
import com.fieldtrackpro.android.performance.Section
import com.fieldtrackpro.android.search.CustomerSearchRanker
import com.fieldtrackpro.android.search.CustomerSearchState
import com.fieldtrackpro.android.ui.screens.planning.AddVisitForm
import com.fieldtrackpro.android.ui.screens.planning.MonthlyPlanContent
import com.fieldtrackpro.android.ui.screens.visits.AdHocVisitForm
import com.fieldtrackpro.android.ui.screens.visits.GpsReadiness
import com.fieldtrackpro.android.ui.theme.FieldTrackProTheme
import com.fieldtrackpro.android.ui.viewmodel.MonthlyPlanUiState
import com.fieldtrackpro.android.ui.viewmodel.PlanLoadError
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.File
import java.io.FileOutputStream
import java.math.BigDecimal
import java.time.LocalDate
import java.util.Calendar

/** Demo-data renders of the Monthly Plan, Add Visit, Off-Beat Visit and Employee Dashboard redesign. */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
abstract class Phase3ScreenshotBase(private val sizeLabel: String) {
    @get:Rule val rule = createAndroidComposeRule<androidx.activity.ComponentActivity>()

    @Before fun gate() = assumeTrue(System.getProperty("captureScreens") == "true")

    private fun shoot(name: String, content: @Composable () -> Unit) {
        rule.setContent { FieldTrackProTheme { content() } }
        rule.waitForIdle()
        val view = rule.activity.findViewById<android.view.View>(android.R.id.content)
        val bmp = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
        view.draw(android.graphics.Canvas(bmp))
        val dir = File(System.getProperty("screensDir") ?: "build/screens").apply { mkdirs() }
        FileOutputStream(File(dir, "${name}_$sizeLabel.png")).use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    private val year = Calendar.getInstance().get(Calendar.YEAR)
    private val month = Calendar.getInstance().get(Calendar.MONTH) + 1
    private fun d(day: Int) = "%04d-%02d-%02d".format(year, month, day)
    private fun pv(id: String, day: Int, name: String, code: String, area: String, status: String, prio: String, notes: String? = null) =
        PlannedVisitDto(id = id, monthlyPlanId = "p", employeeId = "e", customerId = "c$id", plannedDate = d(day), status = status, priority = prio,
            customerName = name, customerOutletCode = code, areaName = area, notes = notes)

    private val plan = MonthlyVisitPlanDto(id = "p", employeeId = "e", year = year, month = month, activeDaysCount = 6, plannedVisits = listOf(
        pv("1", 3, "Demo Kirana Store", "OUT-101", "Kidwai Nagar", "COMPLETED", "HIGH"),
        pv("2", 3, "Sample Traders", "OUT-102", "Civil Lines", "COMPLETED", "MEDIUM"),
        pv("3", 12, "Example Agencies", "OUT-103", "Swaroop Nagar", "COMPLETED", "LOW"),
        pv("4", 24, "Test Mart", "OUT-104", "Kidwai Nagar", "PLANNED", "HIGH", "Payment follow-up"),
        pv("5", 24, "Demo Electricals", "OUT-105", "Govind Nagar", "PLANNED", "MEDIUM"),
        pv("6", 27, "Sample Hardware", "OUT-106", "Civil Lines", "PLANNED", "MEDIUM", "New scheme")
    ))
    private val loaded = MonthlyPlanUiState(year = year, month = month, plan = plan,
        analytics = EmployeeMonthlyAnalyticsDto(employeeId = "e", employeeName = "Demo", year = year, month = month, totalPlanned = 6, completed = 3))

    private fun c(id: String, name: String, code: String, area: String) = CustomerDto(id = id, name = name, outletCode = code, areaName = area, territoryName = "Kanpur")
    private val results = CustomerSearchState(
        query = "sha",
        results = CustomerSearchRanker.rank(listOf(
            c("1", "Sharma Traders", "OUT-201", "Civil Lines") to true,
            c("2", "Shanti Kirana", "OUT-202", "Kidwai Nagar") to true,
            c("3", "Akshay Stores", "OUT-203", "Shastri Nagar") to true,
            c("4", "Mishra Agencies", "OUT-204", "Govind Nagar") to false
        ), "sha")
    )

    @Composable
    private fun sheetFrame(content: @Composable () -> Unit) {
        Box(Modifier.fillMaxSize().background(Color(0xFF0B1426).copy(alpha = 0.5f)), contentAlignment = Alignment.BottomCenter) {
            Surface(shape = RoundedCornerShape(topStart = 24.dp, topEnd = 24.dp), color = Color.White, modifier = Modifier.fillMaxWidth()) {
                Box(Modifier.background(Color.White)) { content() }
            }
        }
    }

    @Test fun planLoaded() = shoot("12_monthly_plan") { MonthlyPlanContent(ui = loaded) }
    @Test fun planCalendar() = shoot("13_monthly_plan_calendar") { MonthlyPlanContent(ui = loaded.copy(calendarView = true, selectedDate = d(24))) }
    @Test fun planUnauthorized() = shoot("14_monthly_plan_401") {
        MonthlyPlanContent(ui = MonthlyPlanUiState(year = year, month = month, loadError = PlanLoadError.UNAUTHORIZED,
            loadErrorMessage = "Your session has ended. Sign in again to see your plan."))
    }
    @Test fun planOffline() = shoot("15_monthly_plan_offline") {
        MonthlyPlanContent(ui = MonthlyPlanUiState(year = year, month = month, loadError = PlanLoadError.NETWORK,
            loadErrorMessage = "Can't reach the server. Check your internet connection and try again."))
    }
    @Test fun addVisitSearching() = shoot("16_add_visit_search") {
        sheetFrame { AddVisitForm(year, month, null, results, false, null, {}, {}, { _, _, _, _ -> }) }
    }
    @Test fun addVisitSelected() = shoot("17_add_visit_selected") {
        sheetFrame { AddVisitForm(year, month, null, CustomerSearchState(), false, null, {}, {}, { _, _, _, _ -> }, preselected = c("1", "Sharma Traders", "OUT-201", "Civil Lines")) }
    }
    @Test fun offBeatSearching() = shoot("18_offbeat_search") {
        sheetFrame { AdHocVisitForm(results, GpsReadiness.READY, false, {}, {}, { _, _, _ -> }) }
    }
    @Test fun offBeatSelected() = shoot("19_offbeat_selected") {
        sheetFrame { AdHocVisitForm(CustomerSearchState(), GpsReadiness.LOCATION_OFF, false, {}, {}, { _, _, _ -> }, preselected = c("4", "Mishra Agencies", "OUT-204", "Govind Nagar")) }
    }

    @Test fun employeeDashboard() = shoot("20_employee_dashboard") {
        val today = LocalDate.now()
        val days = (1..today.dayOfMonth).map { i ->
            EmployeeDashboardCalculator.DayActivity(today.withDayOfMonth(i), i % 7 != 0, 6, 5,
                BigDecimal(if (i % 3 == 0) 0 else 4200 + i * 310), BigDecimal(if (i % 3 == 0 || i > today.dayOfMonth - 2) 0 else 4200 + i * 310))
        }
        val rows = listOf(
            EmployeeDashboardCalculator.OutletRow(c("1", "Demo Kirana Store", "OUT-101", "Kidwai Nagar"), BigDecimal("84500"), BigDecimal("32000"), today.minusDays(2), today.minusDays(9), BigDecimal("15000"),
                mapOf(EmployeeDashboardCalculator.AgeBucket.NOT_DUE to BigDecimal("52500"), EmployeeDashboardCalculator.AgeBucket.D31_60 to BigDecimal("32000"))),
            EmployeeDashboardCalculator.OutletRow(c("2", "Sample Traders", "OUT-102", "Civil Lines"), BigDecimal("41250.50"), BigDecimal.ZERO, today.minusDays(5), today.minusDays(20), BigDecimal("8000"),
                mapOf(EmployeeDashboardCalculator.AgeBucket.D1_30 to BigDecimal("41250.50"))),
            EmployeeDashboardCalculator.OutletRow(c("3", "Example Agencies", "OUT-103", "Swaroop Nagar"), BigDecimal("12800"), BigDecimal("12800"), today.minusDays(30), null, null,
                mapOf(EmployeeDashboardCalculator.AgeBucket.D90_PLUS to BigDecimal("12800"))),
            EmployeeDashboardCalculator.OutletRow(c("4", "Test Mart", "OUT-104", "Kidwai Nagar"), BigDecimal.ZERO, BigDecimal.ZERO, today.minusDays(1), today.minusDays(1), BigDecimal("5000"), emptyMap())
        )
        EmployeeDashboardContent(
            EmployeeDashboardState(
                month = today.withDayOfMonth(1),
                collections = Section.Ready(EmployeeDashboardCalculator.collections(days, today, days.size)),
                performance = Section.Ready(EmployeeDashboardCalculator.FieldPerformance(42, 31, 74, 3, 4, 19, 120, 104)),
                portfolio = Section.Ready(PortfolioData(rows, EmployeeDashboardCalculator.portfolio(rows)))
            )
        )
    }
}

@Config(sdk = [34], qualifiers = "w360dp-h740dp-xhdpi", application = android.app.Application::class)
class Phase3SmallPhone : Phase3ScreenshotBase("360x740")

@Config(sdk = [34], qualifiers = "w393dp-h852dp-xxhdpi", application = android.app.Application::class)
class Phase3MediumPhone : Phase3ScreenshotBase("393x852")

@Config(sdk = [34], qualifiers = "w393dp-h2400dp-xxhdpi", application = android.app.Application::class)
class Phase3FullLength : Phase3ScreenshotBase("393xfull")
