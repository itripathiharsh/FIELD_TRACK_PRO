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
import com.google.gson.reflect.TypeToken
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

class FormFillViewModel(tokenManager: TokenManager) : ViewModel() {
    private val repository = FormTemplateRepository(ApiClient.createFormTemplateApi(tokenManager))
    private val mediaRepository = MediaRepository(ApiClient.createMediaApi(tokenManager))
    private val gson = Gson()

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
            when (val templateResult = repository.renderForm(formId)) {
                is Resource.Success -> {
                    val formRender = templateResult.data
                    _form.value = formRender

                    when (val subResult = repository.getSubmissionForVisit(formId = formId, visitId = visitId)) {
                        is Resource.Success -> {
                            val sub = subResult.data
                            if (sub != null) {
                                submissionId = sub.id
                                val answerMap = sub.answers.associate { it.questionId to it.answerValue }
                                _answers.value = answerMap
                                _isReadOnly.value = (sub.status == "SUBMITTED")
                            } else {
                                submissionId = null
                                _answers.value = emptyMap()
                                _isReadOnly.value = false
                            }
                            _state.value = FormFillState.Ready
                        }
                        is Resource.Error -> {
                            _state.value = FormFillState.Error(subResult.message)
                        }
                        else -> {
                            _state.value = FormFillState.Ready
                        }
                    }
                }
                is Resource.Error -> {
                    _state.value = FormFillState.Error(templateResult.message)
                }
                else -> {}
            }
        }
    }

    fun setAnswer(questionId: String, value: String?) {
        if (_isReadOnly.value) return
        val updated = _answers.value.toMutableMap()
        if (value.isNullOrBlank()) {
            updated.remove(questionId)
        } else {
            updated[questionId] = value
        }
        _answers.value = updated

        if (_fieldErrors.value.containsKey(questionId)) {
            val errors = _fieldErrors.value.toMutableMap()
            errors.remove(questionId)
            _fieldErrors.value = errors
        }

        saveDraft()
    }

    fun toggleCheckboxOption(questionId: String, optionValue: String) {
        if (_isReadOnly.value) return
        val currentList = decodeCheckboxValues(_answers.value[questionId]).toMutableList()
        if (currentList.contains(optionValue)) {
            currentList.remove(optionValue)
        } else {
            currentList.add(optionValue)
        }
        val encoded = if (currentList.isEmpty()) null else gson.toJson(currentList)
        setAnswer(questionId, encoded)
    }

    fun decodeCheckboxValues(raw: String?): List<String> {
        if (raw.isNullOrBlank()) return emptyList()
        return try {
            val type = object : TypeToken<List<String>>() {}.type
            gson.fromJson(raw, type) ?: emptyList()
        } catch (e: Exception) {
            emptyList()
        }
    }

    fun uploadAttachment(questionId: String, fileName: String, mimeType: String, bytes: ByteArray) {
        if (visitId.isBlank() || _isReadOnly.value) return
        viewModelScope.launch {
            when (val res = mediaRepository.uploadVisitMedia(visitId, fileName, mimeType, bytes)) {
                is Resource.Success -> {
                    setAnswer(questionId, res.data.id)
                }
                is Resource.Error -> {
                    val errors = _fieldErrors.value.toMutableMap()
                    errors[questionId] = "Upload failed: ${res.message}"
                    _fieldErrors.value = errors
                }
                else -> {}
            }
        }
    }

    private fun saveDraft() {
        if (visitId.isBlank() || formId.isBlank() || _isReadOnly.value) return
        viewModelScope.launch {
            val saveRes = repository.saveDraft(formId = formId, visitId = visitId, answers = _answers.value)
            if (saveRes is Resource.Success) {
                submissionId = saveRes.data.id
            }
        }
    }

    fun submit(onSuccess: () -> Unit = {}) {
        val form = _form.value ?: return
        val currentAnswers = _answers.value
        val errors = mutableMapOf<String, String>()

        for (section in form.sections) {
            for (field in section.questions) {
                if (field.required) {
                    val answer = currentAnswers[field.id]
                    if (answer.isNullOrBlank()) {
                        errors[field.id] = "${field.questionText} is required"
                    }
                }
            }
        }

        if (errors.isNotEmpty()) {
            _fieldErrors.value = errors
            return
        }

        viewModelScope.launch {
            _state.value = FormFillState.Loading
            var subId = submissionId
            if (subId == null) {
                val saveRes = repository.saveDraft(formId = formId, visitId = visitId, answers = currentAnswers)
                if (saveRes is Resource.Success) {
                    subId = saveRes.data.id
                    submissionId = subId
                } else {
                    _state.value = FormFillState.Error("Could not save form draft before submission")
                    return@launch
                }
            }

            when (val submitRes = repository.submit(subId)) {
                is Resource.Success -> {
                    _isReadOnly.value = true
                    _state.value = FormFillState.Submitted
                    onSuccess()
                }
                is Resource.Error -> {
                    _state.value = FormFillState.Error(submitRes.message)
                }
                else -> {}
            }
        }
    }

    fun resetState() {
        _state.value = FormFillState.Loading
        _form.value = null
        _answers.value = emptyMap()
        _fieldErrors.value = emptyMap()
        _isReadOnly.value = false
        submissionId = null
        visitId = ""
        formId = ""
    }
}
