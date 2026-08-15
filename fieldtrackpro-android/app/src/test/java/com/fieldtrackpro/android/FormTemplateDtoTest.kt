package com.fieldtrackpro.android

import com.fieldtrackpro.android.data.model.AnswerSubmitDto
import com.fieldtrackpro.android.data.model.FormOptionDto
import com.fieldtrackpro.android.data.model.FormQuestionDto
import com.fieldtrackpro.android.data.model.FormRenderDto
import com.fieldtrackpro.android.data.model.FormSectionDto
import com.fieldtrackpro.android.data.model.FormSubmissionDto
import com.fieldtrackpro.android.data.model.SubmissionCreateRequest
import com.google.gson.Gson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Form Template Builder DTO contract tests - mirrors DtoContractTest's
 * pattern. Confirms request DTOs serialize with the exact snake_case field
 * names app/schemas/form_template.py expects, and response DTOs deserialize
 * a real backend payload shape correctly.
 */
class FormTemplateDtoTest {

    private val gson = Gson()

    @Test
    fun submissionCreateRequest_serializesSnakeCaseFieldNames() {
        val request = SubmissionCreateRequest(
            formId = "form-1",
            visitId = "visit-1",
            answers = listOf(AnswerSubmitDto(questionId = "q-1", answerValue = "VH-1002"))
        )
        val json = gson.toJson(request)
        assertTrue("Should contain form_id", json.contains("\"form_id\":\"form-1\""))
        assertTrue("Should contain visit_id", json.contains("\"visit_id\":\"visit-1\""))
        assertTrue("Should contain question_id inside answers", json.contains("\"question_id\":\"q-1\""))
        assertTrue("Should contain answer_value inside answers", json.contains("\"answer_value\":\"VH-1002\""))
        assertTrue("Should NOT contain camelCase formId", !json.contains("\"formId\""))
    }

    @Test
    fun answerSubmitDto_nullAnswerValueOmitsTheField() {
        // Gson's default (no serializeNulls()) omits null fields rather than
        // writing a literal `null`. That's still a valid request: the
        // backend's AnswerSubmit.answer_value is Optional[str] = None, so a
        // missing key and an explicit null parse identically server-side.
        val answer = AnswerSubmitDto(questionId = "q-1", answerValue = null)
        val json = gson.toJson(answer)
        assertTrue("Should contain question_id", json.contains("\"question_id\":\"q-1\""))
        assertTrue("Should omit answer_value rather than write a stray key", !json.contains("answer_value"))
    }

    @Test
    fun formRenderDto_deserializesRealBackendShape() {
        val json = """
            {
              "id": "form-1",
              "name": "Safety Inspection",
              "description": "Checklist",
              "version": 1,
              "status": "PUBLISHED",
              "sections": [
                {
                  "id": "sec-1",
                  "form_id": "form-1",
                  "title": "Vehicle Information",
                  "description": null,
                  "display_order": 0,
                  "questions": [
                    {
                      "id": "q-1",
                      "section_id": "sec-1",
                      "form_id": "form-1",
                      "question_text": "Vehicle condition",
                      "help_text": null,
                      "question_type": "MULTIPLE_CHOICE",
                      "required": true,
                      "display_order": 0,
                      "placeholder": null,
                      "validation_config": null,
                      "options": [
                        {"id": "o1", "question_id": "q-1", "label": "Good", "value": "good", "display_order": 0}
                      ]
                    }
                  ]
                }
              ]
            }
        """.trimIndent()

        val form = gson.fromJson(json, FormRenderDto::class.java)
        assertEquals("Safety Inspection", form.name)
        assertEquals(1, form.sections.size)
        assertEquals("Vehicle Information", form.sections[0].title)
        val question = form.sections[0].questions[0]
        assertEquals("MULTIPLE_CHOICE", question.questionType)
        assertEquals(true, question.required)
        assertEquals(1, question.options.size)
        assertEquals("good", question.options[0].value)
    }

    @Test
    fun formSubmissionDto_deserializesAnswersWithEnrichedQuestionText() {
        val json = """
            {
              "id": "sub-1", "form_id": "form-1", "form_version": 1, "visit_id": "visit-1",
              "submitted_by": "user-1", "status": "SUBMITTED", "started_at": "2026-08-12T00:00:00Z",
              "submitted_at": "2026-08-12T00:05:00Z", "form_name": "Safety Inspection", "employee_name": "Test Rep",
              "answers": [
                {"id": "a1", "submission_id": "sub-1", "question_id": "q-1", "answer_value": "VH-1002", "question_text": "Vehicle ID", "question_type": "SHORT_TEXT"}
              ]
            }
        """.trimIndent()

        val submission = gson.fromJson(json, FormSubmissionDto::class.java)
        assertEquals("SUBMITTED", submission.status)
        assertEquals(1, submission.answers.size)
        assertEquals("VH-1002", submission.answers[0].answerValue)
        assertEquals("Vehicle ID", submission.answers[0].questionText)
    }

    @Test
    fun checkboxAnswers_encodeAndDecodeAsJsonArray() {
        // Mirrors FormFillViewModel.toggleCheckboxOption / decodeCheckboxValues
        // and the web client's identical JSON.stringify([...]) convention, so
        // an answer recorded on one platform reads back correctly on the other.
        val selected = listOf("fire_ext", "first_aid")
        val encoded = gson.toJson(selected)

        @Suppress("UNCHECKED_CAST")
        val decoded = gson.fromJson(encoded, List::class.java) as List<String>

        assertEquals(selected, decoded)
        assertEquals("[\"fire_ext\",\"first_aid\"]", encoded)
    }
}
