package com.fieldtrackpro.android.ui.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.EmployeeWorkdayResponseDto
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.data.repository.WorkdayRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class WorkdayUiState(
    val isLoading: Boolean = false,
    val isSubmitting: Boolean = false,
    val workday: EmployeeWorkdayResponseDto? = null,
    /** True once today's workday has been loaded from the server at least once (null workday then means "not started"). */
    val loadedOnce: Boolean = false,
    val errorMessage: String? = null,
    val actionSuccessMessage: String? = null
)

class WorkdayViewModel(application: Application) : AndroidViewModel(application) {

    private val tokenManager = TokenManager.getInstance(application)
    private val offlineQueueManager = OfflineQueueManager.getInstance(application)
    private val workdayRepository = WorkdayRepository(
        workdayApi = ApiClient.createWorkdayApi(tokenManager),
        offlineQueueManager = offlineQueueManager,
        tokenManager = tokenManager
    )

    private val _uiState = MutableStateFlow(WorkdayUiState())
    val uiState: StateFlow<WorkdayUiState> = _uiState.asStateFlow()

    // No init{} load: the dashboard requests the workday once when it opens (it used to be fetched twice).

    fun loadTodayWorkday() {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, errorMessage = null) }
            when (val res = workdayRepository.getTodayWorkday()) {
                is Resource.Success -> {
                    _uiState.update { it.copy(isLoading = false, workday = res.data, loadedOnce = true, errorMessage = null) }
                }
                is Resource.Error -> {
                    _uiState.update { it.copy(isLoading = false, errorMessage = res.message) }
                }
                is Resource.Loading -> {
                    _uiState.update { it.copy(isLoading = true) }
                }
            }
        }
    }

    fun startDay(
        latitude: Double,
        longitude: Double,
        accuracyM: Double? = null,
        notes: String? = null,
        onSuccess: (() -> Unit)? = null
    ) {
        if (_uiState.value.isSubmitting) return // double-tap guard
        _uiState.update { it.copy(isSubmitting = true, errorMessage = null, actionSuccessMessage = null) }
        viewModelScope.launch {
            when (val res = workdayRepository.startDay(latitude, longitude, accuracyM, notes)) {
                is Resource.Success -> {
                    _uiState.update {
                        it.copy(
                            isSubmitting = false,
                            workday = res.data,
                            actionSuccessMessage = "Workday started successfully!",
                            errorMessage = null
                        )
                    }
                    onSuccess?.invoke()
                }
                is Resource.Error -> {
                    _uiState.update { it.copy(isSubmitting = false, errorMessage = res.message) }
                }
                is Resource.Loading -> {
                    _uiState.update { it.copy(isSubmitting = true) }
                }
            }
        }
    }

    fun endDay(
        latitude: Double,
        longitude: Double,
        accuracyM: Double? = null,
        notes: String? = null,
        onSuccess: (() -> Unit)? = null
    ) {
        if (_uiState.value.isSubmitting) return // double-tap guard
        _uiState.update { it.copy(isSubmitting = true, errorMessage = null, actionSuccessMessage = null) }
        viewModelScope.launch {
            when (val res = workdayRepository.endDay(latitude, longitude, accuracyM, notes)) {
                is Resource.Success -> {
                    _uiState.update {
                        it.copy(
                            isSubmitting = false,
                            workday = res.data,
                            actionSuccessMessage = "Workday completed successfully!",
                            errorMessage = null
                        )
                    }
                    onSuccess?.invoke()
                }
                is Resource.Error -> {
                    _uiState.update { it.copy(isSubmitting = false, errorMessage = res.message) }
                }
                is Resource.Loading -> {
                    _uiState.update { it.copy(isSubmitting = true) }
                }
            }
        }
    }

    /** Shows a message produced outside the view-model (e.g. a rejected GPS fix) in the same place as API errors. */
    fun showError(message: String) {
        _uiState.update { it.copy(errorMessage = message, actionSuccessMessage = null) }
    }

    fun clearMessages() {
        _uiState.update { it.copy(errorMessage = null, actionSuccessMessage = null) }
    }
}
