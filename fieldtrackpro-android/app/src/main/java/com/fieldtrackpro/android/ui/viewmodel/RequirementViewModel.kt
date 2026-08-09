package com.fieldtrackpro.android.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.RequirementCategoryDto
import com.fieldtrackpro.android.data.model.RequirementFormDto
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.RequirementRepository
import com.fieldtrackpro.android.data.repository.Resource
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed class RequirementState {
    object Idle : RequirementState()
    object Loading : RequirementState()
    data class CategoriesLoaded(val categories: List<RequirementCategoryDto>) : RequirementState()
    data class FormLoaded(val form: RequirementFormDto) : RequirementState()
    object FormSubmitted : RequirementState()
    data class Error(val message: String) : RequirementState()
}

class RequirementViewModel(private val tokenManager: TokenManager) : ViewModel() {

    private val repository = RequirementRepository(ApiClient.createRequirementApi(tokenManager))

    private val _state = MutableStateFlow<RequirementState>(RequirementState.Idle)
    val state: StateFlow<RequirementState> = _state.asStateFlow()

    private val _categories = MutableStateFlow<List<RequirementCategoryDto>>(emptyList())
    val categories: StateFlow<List<RequirementCategoryDto>> = _categories.asStateFlow()

    private val _existingForm = MutableStateFlow<RequirementFormDto?>(null)
    val existingForm: StateFlow<RequirementFormDto?> = _existingForm.asStateFlow()

    fun loadCategories() {
        viewModelScope.launch {
            _state.value = RequirementState.Loading
            when (val res = repository.getCategories()) {
                is Resource.Success -> {
                    _categories.value = res.data
                    _state.value = RequirementState.CategoriesLoaded(res.data)
                }
                is Resource.Error -> {
                    _state.value = RequirementState.Error(res.message)
                }
                else -> {}
            }
        }
    }

    fun loadForm(visitId: String) {
        viewModelScope.launch {
            _state.value = RequirementState.Loading
            when (val res = repository.getFormByVisit(visitId)) {
                is Resource.Success -> {
                    _existingForm.value = res.data
                    if (res.data != null) {
                        _state.value = RequirementState.FormLoaded(res.data)
                    } else {
                        _state.value = RequirementState.Idle
                    }
                }
                is Resource.Error -> {
                    _state.value = RequirementState.Error(res.message)
                }
                else -> {}
            }
        }
    }

    fun submitForm(
        visitId: String,
        categoryId: String,
        description: String,
        priority: String,
        expectedTimeline: String,
        budgetRange: String? = null,
        notes: String? = null
    ) {
        viewModelScope.launch {
            _state.value = RequirementState.Loading
            val res = repository.submitForm(
                visitId = visitId,
                categoryId = categoryId,
                description = description,
                priority = priority,
                expectedTimeline = expectedTimeline,
                budgetRange = budgetRange,
                notes = notes
            )
            _state.value = when (res) {
                is Resource.Success -> RequirementState.FormSubmitted
                is Resource.Error -> RequirementState.Error(res.message)
                else -> RequirementState.Error("Unknown error")
            }
        }
    }

    fun reset() {
        _state.value = RequirementState.Idle
    }
}
