package com.fieldtrackpro.android.data.model

import com.google.gson.annotations.SerializedName

/**
 * Visit and geo DTOs.
 *
 * FT-025: `VisitDto` declared eight fields the API has never returned
 * (`scheduled_start_time`, `scheduled_end_time`, `purpose`, `notes`,
 * `actual_check_in_time`, `actual_check_out_time`,
 * `verification_failure_count`, `customer_address`). Several were non-null
 * Kotlin types, so Gson would populate them with null and the screen would
 * fail with a NullPointerException at first use.
 *
 * FT-026: `LocationVerifyResponse` read `allowed_radius_m`; the API field is
 * `geofence_radius_m`, so the radius always deserialised to 0.0 and the
 * geofence UI could not describe the rule it was enforcing.
 *
 * Verified against the live OpenAPI schema for VisitRead, CheckInRequest,
 * CheckOutRequest, LocationVerifyResponse and GeoVerificationLogRead.
 */

/** Response of GET /api/v1/visits and /visits/{id} (VisitRead). */
data class VisitDto(
    val id: String,
    @SerializedName("customer_id") val customerId: String,
    @SerializedName("employee_id") val employeeId: String,
    @SerializedName("scheduled_at") val scheduledAt: String,
    val status: String,
    @SerializedName("check_in_at") val checkInAt: String? = null,
    @SerializedName("check_out_at") val checkOutAt: String? = null,
    val synced: Boolean = false,
    @SerializedName("created_by") val createdBy: String? = null,
    @SerializedName("created_at") val createdAt: String? = null,
    @SerializedName("updated_at") val updatedAt: String? = null,
    @kotlin.jvm.Transient val customerName: String? = null,
    @kotlin.jvm.Transient val customerAddress: String? = null
) {
    val isPending: Boolean get() = status == "PENDING"
    val isInProgress: Boolean get() = status == "IN_PROGRESS"
    val isComplete: Boolean get() = status == "COMPLETED"

    /** Check-in is offered for a visit that has not yet started. */
    val canCheckIn: Boolean get() = status == "PENDING" || status == "FLAGGED"

    /** Check-out is offered once the visit is under way or flagged for review. */
    val canCheckOut: Boolean get() = status == "IN_PROGRESS" || status == "FLAGGED"
}

data class CheckInRequest(
    val latitude: Double,
    val longitude: Double,
    @SerializedName("accuracy_m") val accuracyM: Double? = null,
    @SerializedName("is_mock_location") val isMockLocation: Boolean = false,
    /**
     * Client-generated key so a replayed offline request is not double-logged.
     * The backend enforces uniqueness per visit.
     */
    @SerializedName("idempotency_key") val idempotencyKey: String? = null
)

data class CheckOutRequest(
    val latitude: Double,
    val longitude: Double,
    @SerializedName("accuracy_m") val accuracyM: Double? = null,
    @SerializedName("is_mock_location") val isMockLocation: Boolean = false
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
    // FT-026: the API field is geofence_radius_m, not allowed_radius_m.
    @SerializedName("geofence_radius_m") val geofenceRadiusM: Double,
    @SerializedName("is_mock") val isMock: Boolean,
    @SerializedName("accuracy_m") val accuracyM: Double? = null,
    @SerializedName("failure_reason") val failureReason: String? = null
)

/** Response of GET /api/v1/visits/{id}/geo-logs (GeoVerificationLogRead). */
data class GeoVerificationLogDto(
    val id: String,
    @SerializedName("visit_id") val visitId: String,
    @SerializedName("verification_type") val verificationType: String,
    @SerializedName("attempted_at") val attemptedAt: String,
    val latitude: Double? = null,
    val longitude: Double? = null,
    @SerializedName("distance_from_customer_m") val distanceFromCustomerM: Double,
    @SerializedName("is_valid") val isValid: Boolean,
    @SerializedName("failure_reason") val failureReason: String? = null,
    @SerializedName("idempotency_key") val idempotencyKey: String? = null
)
