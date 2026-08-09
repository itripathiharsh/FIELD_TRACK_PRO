package com.fieldtrackpro.android.data.api

import com.fieldtrackpro.android.data.model.RequirementCategoryDto
import com.fieldtrackpro.android.data.model.RequirementFormDto
import com.fieldtrackpro.android.data.model.RequirementFormRequest
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path

interface RequirementApi {
    @GET("api/v1/requirement-categories")
    suspend fun getCategories(): Response<List<RequirementCategoryDto>>

    @POST("api/v1/requirement-categories")
    suspend fun createCategory(
        @Body category: Map<String, String>
    ): Response<RequirementCategoryDto>

    @POST("api/v1/visits/{visit_id}/requirement-form")
    suspend fun submitForm(
        @Path("visit_id") visitId: String,
        @Body request: RequirementFormRequest
    ): Response<RequirementFormDto>

    @GET("api/v1/visits/{visit_id}/requirement-form")
    suspend fun getForm(
        @Path("visit_id") visitId: String
    ): Response<RequirementFormDto>
}
