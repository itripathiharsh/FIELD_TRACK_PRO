package com.fieldtrackpro.android.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.LocationVerifyResponse
import com.fieldtrackpro.android.data.model.VisitDto
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.data.repository.VisitRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed class CheckInState {
    object Idle : CheckInState()
    object Processing : CheckInState()
    data class VerifySuccess(val verify: LocationVerifyResponse) : CheckInState()
    data class ActionSuccess(val visit: VisitDto, val message: String) : CheckInState()
    data class Error(val message: String) : CheckInState()
}

class CheckInViewModel(
    tokenManager: TokenManager,
    offlineQueueManager: OfflineQueueManager
) : ViewModel() {

    private val repository = VisitRepository(
        visitApi = ApiClient.createVisitApi(tokenManager),
        customerApi = ApiClient.createCustomerApi(tokenManager),
        geoApi = ApiClient.createGeoApi(tokenManager),
        offlineQueueManager = offlineQueueManager
    )

    private val _state = MutableStateFlow<CheckInState>(CheckInState.Idle)
    val state: StateFlow<CheckInState> = _state.asStateFlow()

    fun verifyLocationPreflight(customerId: String, lat: Double, lon: Double) {
        viewModelScope.launch {
            _state.value = CheckInState.Processing
            when (val res = repository.verifyLocation(customerId, lat, lon)) {
                is Resource.Success -> _state.value = CheckInState.VerifySuccess(res.data)
                is Resource.Error -> _state.value = CheckInState.Error(res.message)
                else -> {}
            }
        }
    }

    fun executeCheckIn(visitId: String, lat: Double, lon: Double, isOfflineMode: Boolean = false) {
        viewModelScope.launch {
            _state.value = CheckInState.Processing
            when (val res = repository.checkIn(visitId, lat, lon, isOfflineMode = isOfflineMode)) {
                is Resource.Success -> _state.value = CheckInState.ActionSuccess(res.data, "Check-in successful!")
                is Resource.Error -> _state.value = CheckInState.Error(res.message)
                else -> {}
            }
        }
    }

    fun executeCheckOut(visitId: String, lat: Double, lon: Double, notes: String?, isOfflineMode: Boolean = false) {
        viewModelScope.launch {
            _state.value = CheckInState.Processing
            when (val res = repository.checkOut(visitId, lat, lon, notes = notes, isOfflineMode = isOfflineMode)) {
                is Resource.Success -> _state.value = CheckInState.ActionSuccess(res.data, "Check-out successful!")
                is Resource.Error -> _state.value = CheckInState.Error(res.message)
                else -> {}
            }
        }
    }
}
