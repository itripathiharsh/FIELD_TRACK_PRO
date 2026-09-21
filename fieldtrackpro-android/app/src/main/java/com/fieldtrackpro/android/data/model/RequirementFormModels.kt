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
 * Request to submit a legacy requirement form.
 */
data class RequirementFormRequest(
    @SerializedName("category_id") val categoryId: String,
    val description: String,
    val priority: String,
    @SerializedName("expected_timeline") val expectedTimeline: String,
    @SerializedName("budget_range") val budgetRange: String? = null,
    val notes: String? = null
)

/**
 * Line item in a multi-item requirement.
 */
data class RequirementItemRequest(
    @SerializedName("brand_name") val brandName: String,
    @SerializedName("product_model") val productModel: String,
    @SerializedName("requested_quantity") val requestedQuantity: Int,
    @SerializedName("expected_rate") val expectedRate: Double,
    val notes: String? = null
)

/**
 * Multi-item customer requirement creation request.
 */
data class CreateRequirementRequest(
    @SerializedName("visit_id") val visitId: String? = null,
    @SerializedName("customer_id") val customerId: String? = null,
    val priority: String = "MEDIUM",
    val notes: String? = null,
    val items: List<RequirementItemRequest>
)
