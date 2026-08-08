package com.fieldtrackpro.android.data.model

import com.google.gson.annotations.SerializedName

data class CustomerDto(
    val id: String,
    val name: String,
    @SerializedName("contact_person") val contactPerson: String?,
    val phone: String?,
    val email: String?,
    val address: String,
    val latitude: Double,
    val longitude: Double,
    @SerializedName("geofence_radius_m") val geofenceRadiusM: Double = 100.0,
    @SerializedName("is_active") val isActive: Boolean = true
)
