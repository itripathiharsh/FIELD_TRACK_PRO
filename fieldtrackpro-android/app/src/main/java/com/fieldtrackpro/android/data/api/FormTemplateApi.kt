package com.fieldtrackpro.android.data.api

import com.fieldtrackpro.android.data.model.FormRenderDto
import com.fieldtrackpro.android.data.model.FormSubmissionDto
import com.fieldtrackpro.android.data.model.FormTemplateSummaryDto
import com.fieldtrackpro.android.data.model.SubmissionCreateRequest
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

interface FormTemplateApi {
    @GET("api/v1/form-templates")
    suspend fun listTemplates(@Query("status") status: String? = null): Response<List<FormTemplateSummaryDto>>

    @GET("api/v1/form-templates/{id}/render")
    suspend fun renderForm(@Path("id") formId: String): Response<FormRenderDto>

    @POST("api/v1/form-submissions")
    suspend fun saveSubmission(@Body request: SubmissionCreateRequest): Response<FormSubmissionDto>

    @POST("api/v1/form-submissions/{id}/submit")
    suspend fun submitSubmission(@Path("id") submissionId: String): Response<FormSubmissionDto>

    @GET("api/v1/form-submissions")
    suspend fun listSubmissions(
        @Query("form_id") formId: String? = null,
        @Query("visit_id") visitId: String? = null
    ): Response<List<FormSubmissionDto>>
}
