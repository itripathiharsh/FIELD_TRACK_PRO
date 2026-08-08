package com.fieldtrackpro.android.data.model

import com.google.gson.annotations.SerializedName

data class VisitDto(
    val id: String,
    @SerializedName("employee_id") val employeeId: String,
    @SerializedName("customer_id") val customerId: String,
    @SerializedName("scheduled_start_time") val scheduledStartTime: String,
    @SerializedName("scheduled_end_time") val scheduledEndTime: String,
    val status: String,
    val purpose: String,
    val notes: String? = null,
    @SerializedName("actual_check_in_time") val actualCheckInTime: String? = null,
    @SerializedName("actual_check_out_time") val actualCheckOutTime: String? = null,
    @SerializedName("verification_failure_count") val verificationFailureCount: Int = 0,
    @SerializedName("customer_name") val customerName: String? = null,
    @SerializedName("customer_address") val customerAddress: String? = null
)

data class CheckInRequest(
    val latitude: Double,
    val longitude: Double,
    @SerializedName("accuracy_m") val accuracyM: Double? = null,
    @SerializedName("is_mock_location") val isMockLocation: Boolean = false
)

data class CheckOutRequest(
    val latitude: Double,
    val longitude: Double,
    @SerializedName("accuracy_m") val accuracyM: Double? = null,
    @SerializedName("is_mock_location") val isMockLocation: Boolean = false,
    val notes: String? = null
)

data class LocationVerifyRequest(
    @SerializedName("customer_id") val customerId: String,
    val latitude: Double,
    val longitude: Double,
    @SerializedName("accuracy_m") val accuracyM: Double? = null,
    @SerializedName("is_mock_location") val isMockLocation: Boolean = false
)

data class LocationVerifyResponse(
    @SerializedName("is_valid") val isValid: Boolean,
    @SerializedName("distance_m") val distanceM: Double,
    @SerializedName("allowed_radius_m") val allowedRadiusM: Double,
    @SerializedName("is_mock") val isMock: Boolean,
    @SerializedName("failure_reason") val failureReason: String? = null
)

data class GeoVerificationLogDto(
    val id: String,
    @SerializedName("visit_id") val visitId: String,
    @SerializedName("verification_type") val verificationType: String,
    val latitude: Double,
    val longitude: Double,
    @SerializedName("distance_from_target_m") val distanceFromTargetM: Double?,
    @SerializedName("is_valid") val isValid: Boolean,
    @SerializedName("failure_reason") val failureReason: String?,
    @SerializedName("created_at") val createdAt: String
)
