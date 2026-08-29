package com.fieldtrackpro.android.data.model

import com.google.gson.annotations.SerializedName

/**
 * Dashboard summary and KPI models.
 *
 * APP-NAV-003: Backend aggregate metrics for dashboard instead of local calculation.
 */
data class DashboardKPIs(
    @SerializedName("total_outlets") val totalOutlets: Int = 0,
    @SerializedName("total_visits") val totalVisits: Int = 0,
    @SerializedName("completed_visits") val completedVisits: Int = 0,
    @SerializedName("pending_visits") val pendingVisits: Int = 0,
    @SerializedName("in_progress_visits") val inProgressVisits: Int = 0,
    @SerializedName("flagged_visits") val flaggedVisits: Int = 0,
    @SerializedName("missed_visits") val missedVisits: Int = 0,
    @SerializedName("gps_verified_visits") val gpsVerifiedVisits: Int = 0,
    @SerializedName("total_exceptions") val totalExceptions: Int = 0,
    @SerializedName("pending_exceptions") val pendingExceptions: Int = 0
)

data class DashboardSummaryDto(
    val period: String = "LIVE",
    @SerializedName("is_historical") val isHistorical: Boolean = false,
    val kpis: DashboardKPIs = DashboardKPIs()
)

data class EmployeeDayDashboardDto(
    @SerializedName("employee_id") val employeeId: String,
    @SerializedName("employee_name") val employeeName: String,
    @SerializedName("assigned_outlets_count") val assignedOutletsCount: Int = 0,
    @SerializedName("today_visits_count") val todayVisitsCount: Int = 0,
    @SerializedName("completed_visits_count") val completedVisitsCount: Int = 0,
    @SerializedName("pending_visits_count") val pendingVisitsCount: Int = 0,
    @SerializedName("in_progress_visits_count") val inProgressVisitsCount: Int = 0,
    @SerializedName("missed_visits_count") val missedVisitsCount: Int = 0,
    @SerializedName("collections_today_count") val collectionsTodayCount: Int = 0,
    @SerializedName("orders_today_count") val ordersTodayCount: Int = 0
)
