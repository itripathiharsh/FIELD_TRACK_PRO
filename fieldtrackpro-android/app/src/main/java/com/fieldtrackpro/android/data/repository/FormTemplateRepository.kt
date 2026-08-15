package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.FormTemplateApi
import com.fieldtrackpro.android.data.model.AnswerSubmitDto
import com.fieldtrackpro.android.data.model.FormRenderDto
import com.fieldtrackpro.android.data.model.FormSubmissionDto
import com.fieldtrackpro.android.data.model.FormTemplateSummaryDto
import com.fieldtrackpro.android.data.model.SubmissionCreateRequest

class FormTemplateRepository(private val api: FormTemplateApi) {

    suspend fun listPublishedForms(): Resource<List<FormTemplateSummaryDto>> {
        return try {
            val response = api.listTemplates(status = "PUBLISHED")
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Failed to load forms (${response.code()})")
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    suspend fun renderForm(formId: String): Resource<FormRenderDto> {
        return try {
            val response = api.renderForm(formId)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Failed to load form (${response.code()})")
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    suspend fun getSubmissionForVisit(formId: String, visitId: String): Resource<FormSubmissionDto?> {
        return try {
            val response = api.listSubmissions(formId = formId, visitId = visitId)
            if (response.isSuccessful) {
                Resource.Success(response.body()?.firstOrNull())
            } else {
                Resource.Error("Failed to load submission (${response.code()})")
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    /** Upserts a draft: the same (form, visit, employee) triple always resolves to one submission. */
    suspend fun saveDraft(formId: String, visitId: String, answers: Map<String, String?>): Resource<FormSubmissionDto> {
        return try {
            val request = SubmissionCreateRequest(
                formId = formId,
                visitId = visitId,
                answers = answers.map { (questionId, value) -> AnswerSubmitDto(questionId, value) }
            )
            val response = api.saveSubmission(request)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                val err = response.errorBody()?.string() ?: "Save failed"
                Resource.Error("Save failed (${response.code()}): $err", response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Save failed: ${e.localizedMessage}")
        }
    }

    suspend fun submit(submissionId: String): Resource<FormSubmissionDto> {
        return try {
            val response = api.submitSubmission(submissionId)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                val err = response.errorBody()?.string() ?: "Submit failed"
                Resource.Error("Submit failed (${response.code()}): $err", response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Submit failed: ${e.localizedMessage}")
        }
    }
}
