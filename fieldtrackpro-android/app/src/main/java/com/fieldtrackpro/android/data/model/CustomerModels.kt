package com.fieldtrackpro.android.data.model

import com.google.gson.annotations.SerializedName

/**
 * Customer DTO and Pagination Models.
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
    val address: String? = null,
    /** Geofence centre. Nested object, not flat lat/lng fields. */
    val location: GeoPointDto? = null,
    @SerializedName("geofence_radius_m") val geofenceRadiusM: Int = 75,
    @SerializedName("location_status") val locationStatus: String? = null,
    @SerializedName("outlet_code") val outletCode: String? = null,
    @SerializedName("dms_code") val dmsCode: String? = null,
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
