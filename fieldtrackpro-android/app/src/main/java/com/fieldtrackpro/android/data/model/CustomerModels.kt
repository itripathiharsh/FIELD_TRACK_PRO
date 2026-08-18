package com.fieldtrackpro.android.data.model

import com.google.gson.annotations.SerializedName

/**
 * Customer DTO.
 *
 * FT-025 (same class of defect as VisitDto): this declared flat `latitude` and
 * `longitude` fields plus `phone` and `is_active`, none of which the API
 * returns. The geofence centre arrives as a nested `location` object, so the
 * coordinates the check-in screen depends on always deserialised to 0.0 -
 * the Android mirror of the FT-004 Null Island defect.
 *
 * Verified against the live OpenAPI schema for CustomerRead.
 */

/** Nested geographic point, matching the API's LocationOut. */
data class GeoPointDto(
    val latitude: Double,
    val longitude: Double
)

data class CustomerDto(
    val id: String,
    val name: String,
    @SerializedName("contact_number") val contactNumber: String,
    @SerializedName("contact_person") val contactPerson: String? = null,
    val address: String,
    /** Geofence centre. Nested object, not flat lat/lng fields. */
    val location: GeoPointDto,
    @SerializedName("geofence_radius_m") val geofenceRadiusM: Int = 75,
    // Zone.
    @SerializedName("territory_id") val territoryId: String? = null,
    // Zone -> Area -> Outlet. Once set, Area is the source of truth for the
    // Zone (kept in sync server-side - see CustomerRead.from_model).
    @SerializedName("area_id") val areaId: String? = null,
    @SerializedName("area_name") val areaName: String? = null,
    @SerializedName("created_by") val createdBy: String? = null,
    @SerializedName("created_at") val createdAt: String? = null
) {
    val latitude: Double get() = location.latitude
    val longitude: Double get() = location.longitude
}
