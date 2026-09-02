package com.fieldtrackpro.android.data.model

import com.google.gson.annotations.SerializedName

/**
 * Data contracts for Employee Workday & Daily Field Activity.
 */
data class WorkSessionStartRequest(
    @SerializedName("latitude") val latitude: Double,
    @SerializedName("longitude") val longitude: Double,
    @SerializedName("accuracy_meters") val accuracyMeters: Double? = null,
    @SerializedName("client_timestamp") val clientTimestamp: String? = null,
    @SerializedName("notes") val notes: String? = null
)

data class WorkSessionEndRequest(
    @SerializedName("latitude") val latitude: Double,
    @SerializedName("longitude") val longitude: Double,
    @SerializedName("accuracy_meters") val accuracyMeters: Double? = null,
    @SerializedName("client_timestamp") val clientTimestamp: String? = null,
    @SerializedName("notes") val notes: String? = null
)

data class WorkSessionDto(
    @SerializedName("id") val id: String,
    @SerializedName("employee_id") val employeeId: String,
    @SerializedName("work_date") val workDate: String,
    @SerializedName("status") val status: String, // "NOT_STARTED", "STARTED", "COMPLETED"
    @SerializedName("start_time") val startTime: String? = null,
    @SerializedName("start_latitude") val startLatitude: Double? = null,
    @SerializedName("start_longitude") val startLongitude: Double? = null,
    @SerializedName("start_accuracy_meters") val startAccuracyMeters: Double? = null,
    @SerializedName("end_time") val endTime: String? = null,
    @SerializedName("end_latitude") val endLatitude: Double? = null,
    @SerializedName("end_longitude") val endLongitude: Double? = null,
    @SerializedName("end_accuracy_meters") val endAccuracyMeters: Double? = null,
    @SerializedName("start_notes") val startNotes: String? = null,
    @SerializedName("end_notes") val endNotes: String? = null,
    @SerializedName("created_at") val createdAt: String? = null,
    @SerializedName("updated_at") val updatedAt: String? = null
)

data class DailyFieldActivitySummaryDto(
    @SerializedName("work_date") val workDate: String,
    @SerializedName("total_visits") val totalVisits: Int = 0,
    @SerializedName("planned_visits") val plannedVisits: Int = 0,
    @SerializedName("adhoc_visits") val adhocVisits: Int = 0,
    @SerializedName("completed_visits") val completedVisits: Int = 0,
    @SerializedName("missed_visits") val missedVisits: Int = 0,
    @SerializedName("flagged_visits") val flaggedVisits: Int = 0,
    @SerializedName("collections_count") val collectionsCount: Int = 0,
    @SerializedName("collections_total_amount") val collectionsTotalAmount: Double = 0.0,
    @SerializedName("collections_verified_amount") val collectionsVerifiedAmount: Double = 0.0
)

data class EmployeeWorkdayResponseDto(
    @SerializedName("employee_id") val employeeId: String,
    @SerializedName("employee_name") val employeeName: String? = null,
    @SerializedName("work_date") val workDate: String,
    @SerializedName("session") val session: WorkSessionDto? = null,
    @SerializedName("summary") val summary: DailyFieldActivitySummaryDto
)
