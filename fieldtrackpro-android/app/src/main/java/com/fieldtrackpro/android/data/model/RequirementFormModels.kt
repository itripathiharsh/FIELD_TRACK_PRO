package com.fieldtrackpro.android.data.model

import com.google.gson.annotations.SerializedName

/**
 * Requirement Category DTO.
 *
 * Aligned with the API's RequirementCategoryRead schema.
 */
data class RequirementCategoryDto(
    val id: String,
    val name: String,
    @SerializedName("is_active") val isActive: Boolean = true
)

/**
 * Requirement Form DTO.
 *
 * Aligned with the API's RequirementFormRead schema.
 */
data class RequirementFormDto(
    val id: String,
    @SerializedName("visit_id") val visitId: String,
    @SerializedName("category_id") val categoryId: String,
    @SerializedName("category_name") val categoryName: String?,
    val description: String,
    val priority: String,
    @SerializedName("expected_timeline") val expectedTimeline: String,
    @SerializedName("budget_range") val budgetRange: String?,
    val notes: String?,
    @SerializedName("submitted_at") val submittedAt: String
)

/**
 * Request to submit a requirement form.
 */
data class RequirementFormRequest(
    @SerializedName("category_id") val categoryId: String,
    val description: String,
    val priority: String,
    @SerializedName("expected_timeline") val expectedTimeline: String,
    @SerializedName("budget_range") val budgetRange: String? = null,
    val notes: String? = null
)
