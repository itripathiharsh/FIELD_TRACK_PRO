package com.fieldtrackpro.android.data.model

import com.google.gson.annotations.SerializedName

/**
 * Monthly Visit Planning Data Transfer Objects
 * Matching backend FastAPI schemas in app.schemas.visit_planning & app.schemas.visit_analytics
 */

data class MonthlyVisitPlanDto(
    @SerializedName("id") val id: String,
    @SerializedName("employee_id") val employeeId: String,
    @SerializedName("year") val year: Int,
    @SerializedName("month") val month: Int,
    @SerializedName("status") val status: String = "ACTIVE",
    @SerializedName("notes") val notes: String? = null,
    @SerializedName("created_by") val createdBy: String? = null,
    @SerializedName("created_at") val createdAt: String? = null,
    @SerializedName("updated_at") val updatedAt: String? = null,
    @SerializedName("employee_name") val employeeName: String? = null,
    @SerializedName("employee_code") val employeeCode: String? = null,
    @SerializedName("planned_visits") val plannedVisits: List<PlannedVisitDto> = emptyList(),
    @SerializedName("total_planned_visits") val totalPlannedVisits: Int = 0,
    @SerializedName("active_days_count") val activeDaysCount: Int = 0
)

data class PlannedVisitDto(
    @SerializedName("id") val id: String,
    @SerializedName("monthly_plan_id") val monthlyPlanId: String,
    @SerializedName("employee_id") val employeeId: String,
    @SerializedName("customer_id") val customerId: String,
    @SerializedName("planned_date") val plannedDate: String,
    @SerializedName("visit_type") val visitType: String = "PLANNED",
    @SerializedName("priority") val priority: String = "MEDIUM",
    @SerializedName("notes") val notes: String? = null,
    @SerializedName("status") val status: String = "PLANNED",
    @SerializedName("created_at") val createdAt: String? = null,
    @SerializedName("updated_at") val updatedAt: String? = null,
    @SerializedName("customer_name") val customerName: String? = null,
    @SerializedName("customer_outlet_code") val customerOutletCode: String? = null,
    @SerializedName("customer_address") val customerAddress: String? = null,
    @SerializedName("employee_name") val employeeName: String? = null,
    @SerializedName("employee_code") val employeeCode: String? = null,
    @SerializedName("area_name") val areaName: String? = null,
    @SerializedName("territory_name") val territoryName: String? = null
)

data class PlannedVisitCreateRequest(
    @SerializedName("customer_id") val customerId: String,
    @SerializedName("planned_date") val plannedDate: String,
    @SerializedName("visit_type") val visitType: String = "PLANNED",
    @SerializedName("priority") val priority: String = "MEDIUM",
    @SerializedName("notes") val notes: String? = null
)

data class PlannedVisitUpdateRequest(
    @SerializedName("priority") val priority: String? = null,
    @SerializedName("notes") val notes: String? = null,
    @SerializedName("visit_type") val visitType: String? = null
)

data class PlannedVisitRescheduleRequest(
    @SerializedName("new_date") val newDate: String
)

data class EmployeeMonthlyAnalyticsDto(
    @SerializedName("employee_id") val employeeId: String,
    @SerializedName("employee_name") val employeeName: String,
    @SerializedName("employee_code") val employeeCode: String? = null,
    @SerializedName("year") val year: Int,
    @SerializedName("month") val month: Int,
    @SerializedName("total_planned") val totalPlanned: Int = 0,
    @SerializedName("completed") val completed: Int = 0,
    @SerializedName("missed") val missed: Int = 0,
    @SerializedName("cancelled") val cancelled: Int = 0,
    @SerializedName("extra_unplanned") val extraUnplanned: Int = 0,
    @SerializedName("completion_rate") val completionRate: Double? = null,
    @SerializedName("active_planned_days") val activePlannedDays: Int = 0,
    @SerializedName("active_execution_days") val activeExecutionDays: Int = 0,
    @SerializedName("avg_planned_per_active_day") val avgPlannedPerActiveDay: Double? = null,
    @SerializedName("avg_completed_per_execution_day") val avgCompletedPerExecutionDay: Double? = null,
    @SerializedName("behind_schedule") val behindSchedule: Boolean = false
)
