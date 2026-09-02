package com.fieldtrackpro.android.data.model

import com.google.gson.annotations.SerializedName

/**
 * Customer DTO, Location Proposals, Requirements, and Prospect Models.
 *
 * APP-CUST-002: Server-side pagination with totalCount preservation from X-Total-Count.
 * APP-CUST-011: territory_name mapping.
 * APP-CUST-013: Null location means "Customer location not configured" (does not default to 0.0).
 */

/** Nested geographic point, matching the API's LocationOut. */
data class GeoPointDto(
    val latitude: Double,
    val longitude: Double
)

data class CustomerDto(
    val id: String,
    val name: String,
    @SerializedName("contact_number") val contactNumber: String? = null,
    @SerializedName("contact_person") val contactPerson: String? = null,
    @SerializedName("gst_number") val gstNumber: String? = null,
    val address: String? = null,
    /** Geofence centre. Nested object, not flat lat/lng fields. */
    val location: GeoPointDto? = null,
    @SerializedName("geofence_radius_m") val geofenceRadiusM: Int = 75,
    @SerializedName("location_status") val locationStatus: String? = null,
    @SerializedName("outlet_code") val outletCode: String? = null,
    @SerializedName("dms_code") val dmsCode: String? = null,
    val brands: List<String> = emptyList(),
    // Zone.
    @SerializedName("territory_id") val territoryId: String? = null,
    @SerializedName("territory_name") val territoryName: String? = null,
    // Zone -> Area -> Outlet.
    @SerializedName("area_id") val areaId: String? = null,
    @SerializedName("area_name") val areaName: String? = null,
    @SerializedName("created_by") val createdBy: String? = null,
    @SerializedName("created_at") val createdAt: String? = null
) {
    val latitude: Double? get() = location?.latitude
    val longitude: Double? get() = location?.longitude
}

/**
 * Encapsulates a paginated list of customers along with server total count.
 */
data class CustomerPage(
    val customers: List<CustomerDto>,
    val totalCount: Int,
    val skip: Int,
    val limit: Int
) {
    val hasMore: Boolean get() = skip + customers.size < totalCount
}

/**
 * DTO for submitting a proposed location update for an existing customer.
 */
data class LocationProposalCreate(
    @SerializedName("proposed_latitude") val proposedLatitude: Double,
    @SerializedName("proposed_longitude") val proposedLongitude: Double,
    @SerializedName("gps_accuracy_meters") val gpsAccuracyMeters: Double? = null,
    val notes: String? = null
)

/**
 * DTO for location proposal read.
 */
data class LocationProposalDto(
    val id: String,
    @SerializedName("customer_id") val customerId: String,
    @SerializedName("customer_name") val customerName: String? = null,
    @SerializedName("customer_outlet_code") val customerOutletCode: String? = null,
    @SerializedName("current_latitude") val currentLatitude: Double? = null,
    @SerializedName("current_longitude") val currentLongitude: Double? = null,
    @SerializedName("proposed_latitude") val proposedLatitude: Double,
    @SerializedName("proposed_longitude") val proposedLongitude: Double,
    @SerializedName("gps_accuracy_meters") val gpsAccuracyMeters: Double? = null,
    @SerializedName("distance_meters") val distanceMeters: Double? = null,
    @SerializedName("submitted_by") val submittedBy: String,
    @SerializedName("submitter_name") val submitterName: String? = null,
    @SerializedName("submitted_at") val submittedAt: String,
    val status: String,
    @SerializedName("rejection_reason") val rejectionReason: String? = null,
    val notes: String? = null,
    @SerializedName("created_at") val createdAt: String? = null
)

/**
 * DTO for customer requirement / business opportunity creation.
 */
data class CustomerRequirementCreate(
    val brand: String? = null,
    @SerializedName("requirement_type") val requirementType: String? = null,
    @SerializedName("product_details") val productDetails: String? = null,
    val quantity: Int? = null,
    @SerializedName("expected_value") val expectedValue: Double? = null,
    @SerializedName("follow_up_date") val followUpDate: String? = null,
    val notes: String? = null
)

/**
 * DTO for customer requirement read.
 */
data class CustomerRequirementDto(
    val id: String,
    @SerializedName("customer_id") val customerId: String,
    val brand: String? = null,
    @SerializedName("requirement_type") val requirementType: String? = null,
    @SerializedName("product_details") val productDetails: String? = null,
    val quantity: Int? = null,
    @SerializedName("expected_value") val expectedValue: Double? = null,
    @SerializedName("follow_up_date") val followUpDate: String? = null,
    val notes: String? = null,
    val status: String,
    @SerializedName("created_by") val createdBy: String,
    @SerializedName("created_at") val createdAt: String? = null
)

/**
 * DTO for submitting a new Customer / Outlet Prospect in the field.
 */
data class CustomerProspectCreate(
    val name: String,
    @SerializedName("contact_number") val contactNumber: String,
    @SerializedName("contact_person") val contactPerson: String? = null,
    @SerializedName("gst_number") val gstNumber: String? = null,
    val address: String? = null,
    @SerializedName("territory_id") val territoryId: String? = null,
    @SerializedName("area_id") val areaId: String? = null,
    @SerializedName("outlet_code") val outletCode: String? = null,
    val brands: List<String> = emptyList(),
    val requirement: CustomerRequirementCreate? = null,
    val location: GeoPointDto? = null,
    @SerializedName("gps_accuracy_meters") val gpsAccuracyMeters: Double? = null,
    val notes: String? = null,
    val force: Boolean = false
)
