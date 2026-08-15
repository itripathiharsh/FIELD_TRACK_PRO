package com.fieldtrackpro.android.data.model

import com.google.gson.annotations.SerializedName

/**
 * Form Template Builder DTOs. Mirror app/schemas/form_template.py exactly -
 * see fieldtrackpro-web/src/types/index.ts for the same contract on web.
 */

data class FormOptionDto(
    val id: String,
    @SerializedName("question_id") val questionId: String,
    val label: String,
    val value: String,
    @SerializedName("display_order") val displayOrder: Int
)

data class FormQuestionDto(
    val id: String,
    @SerializedName("section_id") val sectionId: String,
    @SerializedName("form_id") val formId: String,
    @SerializedName("question_text") val questionText: String,
    @SerializedName("help_text") val helpText: String?,
    @SerializedName("question_type") val questionType: String,
    val required: Boolean,
    @SerializedName("display_order") val displayOrder: Int,
    val placeholder: String?,
    @SerializedName("validation_config") val validationConfig: Map<String, Any>?,
    val options: List<FormOptionDto> = emptyList()
)

data class FormSectionDto(
    val id: String,
    @SerializedName("form_id") val formId: String,
    val title: String,
    val description: String?,
    @SerializedName("display_order") val displayOrder: Int,
    val questions: List<FormQuestionDto> = emptyList()
)

/** Response of GET /form-templates/{id}/render - what an employee fills in. */
data class FormRenderDto(
    val id: String,
    val name: String,
    val description: String?,
    val version: Int,
    val status: String,
    val sections: List<FormSectionDto> = emptyList()
)

/** Response of GET /form-templates (list), filtered to status=PUBLISHED for the employee flow. */
data class FormTemplateSummaryDto(
    val id: String,
    val name: String,
    val description: String?,
    val status: String,
    val version: Int,
    @SerializedName("question_count") val questionCount: Int
)

data class AnswerSubmitDto(
    @SerializedName("question_id") val questionId: String,
    @SerializedName("answer_value") val answerValue: String?
)

data class SubmissionCreateRequest(
    @SerializedName("form_id") val formId: String,
    @SerializedName("visit_id") val visitId: String,
    val answers: List<AnswerSubmitDto>
)

data class FormAnswerDto(
    val id: String,
    @SerializedName("submission_id") val submissionId: String,
    @SerializedName("question_id") val questionId: String,
    @SerializedName("answer_value") val answerValue: String?,
    @SerializedName("question_text") val questionText: String?,
    @SerializedName("question_type") val questionType: String?
)

/** Response of POST /form-submissions[/{id}/submit] and GET /form-submissions. */
data class FormSubmissionDto(
    val id: String,
    @SerializedName("form_id") val formId: String,
    @SerializedName("form_version") val formVersion: Int,
    @SerializedName("visit_id") val visitId: String,
    @SerializedName("submitted_by") val submittedBy: String,
    val status: String,
    @SerializedName("started_at") val startedAt: String,
    @SerializedName("submitted_at") val submittedAt: String?,
    @SerializedName("form_name") val formName: String?,
    @SerializedName("employee_name") val employeeName: String?,
    val answers: List<FormAnswerDto> = emptyList()
)
