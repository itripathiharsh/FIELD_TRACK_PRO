package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.RequirementApi
import com.fieldtrackpro.android.data.model.RequirementCategoryDto
import com.fieldtrackpro.android.data.model.RequirementFormDto
import com.fieldtrackpro.android.data.model.RequirementFormRequest

class RequirementRepository(private val requirementApi: RequirementApi) {

    suspend fun getCategories(): Resource<List<RequirementCategoryDto>> {
        return try {
            val response = requirementApi.getCategories()
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Failed to load categories (${response.code()})")
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    suspend fun submitForm(
        visitId: String,
        categoryId: String,
        description: String,
        priority: String,
        expectedTimeline: String,
        budgetRange: String? = null,
        notes: String? = null
    ): Resource<RequirementFormDto> {
        return try {
            val request = RequirementFormRequest(
                categoryId = categoryId,
                description = description,
                priority = priority,
                expectedTimeline = expectedTimeline,
                budgetRange = budgetRange,
                notes = notes
            )
            val response = requirementApi.submitForm(visitId, request)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                val err = response.errorBody()?.string() ?: "Form submission failed"
                Resource.Error("Submit failed (${response.code()}): $err", response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Submit failed: ${e.localizedMessage}")
        }
    }

    suspend fun getFormByVisit(visitId: String): Resource<RequirementFormDto?> {
        return try {
            val response = requirementApi.getForm(visitId)
            if (response.isSuccessful) {
                Resource.Success(response.body())
            } else {
                Resource.Error("Failed to load form (${response.code()})")
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }
}
