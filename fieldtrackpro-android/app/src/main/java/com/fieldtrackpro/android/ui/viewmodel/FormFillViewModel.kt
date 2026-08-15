package com.fieldtrackpro.android.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.FormRenderDto
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.FormTemplateRepository
import com.fieldtrackpro.android.data.repository.MediaRepository
import com.fieldtrackpro.android.data.repository.Resource
import com.google.gson.Gson
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed class FormFillState {
    object Loading : FormFillState()
    object Ready : FormFillState()
    object Submitted : FormFillState()
    data class Error(val message: String) : FormFillState()
}

/**
 * Drives the employee-facing form-fill screen: loads a published form's live
 * structure, restores any existing draft/submission for this visit, keeps
 * answers as local state with an auto-save draft on every change, validates
 * required questions before the final submit, and uploads
 * FILE_UPLOAD/PHOTO_UPLOAD answers through the existing visit-media endpoint
 * (never a separate upload path - Part 10 requires reusing existing media
 * infrastructure).
 */
class FormFillViewModel(tokenManager: TokenManager) : ViewModel() {
    private val repository = FormTemplateRepository(ApiClient.createFormTemplateApi(tokenManager))
    private val mediaRepository = MediaRepository(ApiClient.createMediaApi(tokenManager))

    private val _state = MutableStateFlow<FormFillState>(FormFillState.Loading)
    val state: StateFlow<FormFillState> = _state.asStateFlow()

    private val _form = MutableStateFlow<FormRenderDto?>(null)
    val form: StateFlow<FormRenderDto?> = _form.asStateFlow()

    private val _answers = MutableStateFlow<Map<String, String?>>(emptyMap())
    val answers: StateFlow<Map<String, String?>> = _answers.asStateFlow()

    private val _fieldErrors = MutableStateFlow<Map<String, String>>(emptyMap())
    val fieldErrors: StateFlow<Map<String, String>> = _fieldErrors.asStateFlow()

    private val _isReadOnly = MutableStateFlow(false)
    val isReadOnly: StateFlow<Boolean> = _isReadOnly.asStateFlow()

    private var submissionId: String? = null
    private var visitId: String = ""
    private var formId: String = ""

    fun load(visitId: String, formId: String) {
        this.visitId = visitId
        this.formId = formId
        viewModelScope.launch {
            _state.value = FormFillState.Loading
            when (val renderRes = repository.renderForm(formId)) {
                is Resource.Success -> _form.value = renderRes.data
                is Resource.Error -> {
                    _state.value = FormFillState.Error(renderRes.message)
                    return@launch
                }
                else -> {}
            }

            when (val subRes = repository.getSubmissionForVisit(formId, visitId)) {
                is Resource.Success -> {
                    val existing = subRes.data
                    if (existing != null) {
                        submissionId = existing.id
                        _answers.value = existing.answers.associate { it.questionId to it.answerValue }
                        _isReadOnly.value = existing.status == "SUBMITTED"
                    }
                }
                is Resource.Error -> {
                    _state.value = FormFillState.Error(subRes.message)
                    return@launch
                }
                else -> {}
            }
            _state.value = FormFillState.Ready
        }
    }

    fun setAnswer(questionId: String, value: String?) {
        _answers.value = _answers.value.toMutableMap().apply { put(questionId, value) }
        _fieldErrors.value = _fieldErrors.value.toMutableMap().apply { remove(questionId) }
        viewModelScope.launch { saveDraft() }
    }

    /** CHECKBOXES answers are multi-valued; encoded the same way as the web client (a JSON array string). */
    fun toggleCheckboxOption(questionId: String, optionValue: String) {
        val current = decodeCheckboxValues(_answers.value[questionId])
        val next = if (current.contains(optionValue)) current - optionValue else current + optionValue
        setAnswer(questionId, if (next.isEmpty()) null else Gson().toJson(next))
    }

    fun decodeCheckboxValues(value: String?): List<String> {
        if (value.isNullOrBlank()) return emptyList()
        return try {
            @Suppress("UNCHECKED_CAST")
            Gson().fromJson(value, List::class.java) as List<String>
        } catch (e: Exception) {
            emptyList()
        }
    }

    /** Reuses the existing visit-media upload endpoint (Part 10: no separate attachment system). */
    fun uploadAttachment(questionId: String, fileName: String, mimeType: String, bytes: ByteArray) {
        viewModelScope.launch {
            when (val res = mediaRepository.uploadVisitMedia(visitId, fileName, mimeType, bytes)) {
                is Resource.Success -> setAnswer(questionId, res.data.id)
                is Resource.Error -> _state.value = FormFillState.Error(res.message)
                else -> {}
            }
        }
    }

    private suspend fun saveDraft() {
        val request = _answers.value
        when (val res = repository.saveDraft(formId, visitId, request)) {
            is Resource.Success -> submissionId = res.data.id
            is Resource.Error -> _state.value = FormFillState.Error(res.message)
            else -> {}
        }
    }

    fun submit() {
        val currentForm = _form.value ?: return
        val missing = currentForm.sections
            .flatMap { it.questions }
            .filter { it.required && _answers.value[it.id].isNullOrBlank() }
        if (missing.isNotEmpty()) {
            _fieldErrors.value = missing.associate { it.id to "This question is required." }
            return
        }

        viewModelScope.launch {
            _state.value = FormFillState.Loading
            saveDraft()
            val id = submissionId
            if (id == null) {
                _state.value = FormFillState.Error("Could not save your answers before submitting.")
                return@launch
            }
            when (val res = repository.submit(id)) {
                is Resource.Success -> {
                    _isReadOnly.value = true
                    _state.value = FormFillState.Submitted
                }
                is Resource.Error -> _state.value = FormFillState.Error(res.message)
                else -> {}
            }
        }
    }
}
