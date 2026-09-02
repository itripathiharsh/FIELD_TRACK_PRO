package com.fieldtrackpro.android.data.model

import com.google.gson.annotations.SerializedName

data class BrandDto(
    val id: String,
    val name: String,
    @SerializedName("normalized_name") val normalizedName: String? = null,
    @SerializedName("is_active") val isActive: Boolean = true,
    @SerializedName("created_at") val createdAt: String? = null,
    @SerializedName("updated_at") val updatedAt: String? = null
)

data class BrandCreate(
    val name: String
)
