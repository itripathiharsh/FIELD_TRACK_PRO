package com.fieldtrackpro.android.ui.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.LocationVerifyResponse
import com.fieldtrackpro.android.data.model.VisitDto
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.data.repository.VisitRepository
import com.fieldtrackpro.android.utils.CoordinateValidator
import com.fieldtrackpro.android.workers.OfflineSyncScheduler
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed class CheckInState {
    object Idle : CheckInState()
    object Processing : CheckInState()
    data class VerifySuccess(val verify: LocationVerifyResponse) : CheckInState()
    data class ActionSuccess(val visit: VisitDto, val message: String) : CheckInState()
    /** Saved to the offline queue and will sync automatically once the device has connectivity - not a rejection. */
    data class Queued(val message: String) : CheckInState()
    data class GeoRejected(val message: String) : CheckInState()
    data class LowAccuracy(val message: String) : CheckInState()
    data class StaleLocation(val message: String) : CheckInState()
    data class InvalidCoordinates(val message: String) : CheckInState()
    data class Conflict(val message: String) : CheckInState()
    data class Error(val message: String) : CheckInState()
}

/**
 * Isolated ViewModel for Visit Check-In.
 *
 * APP-ATT-001: Focuses solely on Check-In; Check-Out state is maintained in CheckOutViewModel.
 * APP-ATT-004: Validates GPS coordinates before dispatch; rejects (0,0) and invalid ranges.
 */
class CheckInViewModel(
    application: Application,
    tokenManager: TokenManager,
    offlineQueueManager: OfflineQueueManager
) : AndroidViewModel(application) {

    private val repository = VisitRepository(
        visitApi = ApiClient.createVisitApi(tokenManager),
        customerApi = ApiClient.createCustomerApi(tokenManager),
        geoApi = ApiClient.createGeoApi(tokenManager),
        offlineQueueManager = offlineQueueManager
    )

    private val _state = MutableStateFlow<CheckInState>(CheckInState.Idle)
    val state: StateFlow<CheckInState> = _state.asStateFlow()

    fun resetState() {
        _state.value = CheckInState.Idle
    }

    fun verifyLocationPreflight(
        customerId: String,
        lat: Double?,
        lon: Double?,
        accuracyM: Double? = 10.0,
        isMock: Boolean = false
    ) {
        if (!CoordinateValidator.isValidCoordinate(lat, lon)) {
            _state.value = CheckInState.InvalidCoordinates(
                "Invalid GPS coordinates. Please capture a fresh location fix."
            )
            return
        }

        viewModelScope.launch {
            _state.value = CheckInState.Processing
            when (val res = repository.verifyLocation(customerId, lat!!, lon!!, accuracyM ?: 10.0, isMock)) {
                is Resource.Success -> _state.value = CheckInState.VerifySuccess(res.data)
                is Resource.Error -> _state.value = parseError(res.message, res.code)
                else -> {}
            }
        }
    }

    fun executeCheckIn(
        visitId: String,
        lat: Double?,
        lon: Double?,
        capturedAtMillis: Long,
        accuracyM: Double? = null,
        isMock: Boolean = false,
        isOfflineMode: Boolean = false,
    ) {
        if (!CoordinateValidator.isValidCoordinate(lat, lon)) {
            _state.value = CheckInState.InvalidCoordinates(
                "Invalid GPS coordinates. Please capture a fresh location fix."
            )
            return
        }

        if (accuracyM == null || accuracyM < 0.0) {
            _state.value = CheckInState.LowAccuracy(
                "Location accuracy unavailable. Please capture a fresh location fix."
            )
            return
        }

        viewModelScope.launch {
            _state.value = CheckInState.Processing
            when (
                val res = repository.checkIn(
                    visitId, lat!!, lon!!,
                    capturedAtMillis = capturedAtMillis,
                    accuracyM = accuracyM,
                    isMock = isMock,
                    isOfflineMode = isOfflineMode,
                )
            ) {
                is Resource.Success -> _state.value = CheckInState.ActionSuccess(res.data, "Check-in verified successfully!")
                is Resource.Error -> {
                    if (res.isQueued) {
                        OfflineSyncScheduler.scheduleSync(getApplication())
                        _state.value = CheckInState.Queued("Check-in saved. It will sync automatically when network returns.")
                    } else {
                        _state.value = parseError(res.message, res.code)
                    }
                }
                else -> {}
            }
        }
    }

    private fun parseError(rawMessage: String, code: Int?): CheckInState {
        val msg = rawMessage.lowercase()
        return when {
            msg.contains("too old") || msg.contains("stale") -> CheckInState.StaleLocation(
                "GPS reading is older than 24 hours. Please capture a fresh location."
            )
            msg.contains("future") -> CheckInState.StaleLocation(
                "GPS timestamp is in the future. Please check device clock settings."
            )
            msg.contains("accuracy") || msg.contains("threshold") -> CheckInState.LowAccuracy(
                "Location accuracy is too low. Move to an open area and try again."
            )
            msg.contains("exceeds allowed radius") || msg.contains("outside") || msg.contains("geofence") -> CheckInState.GeoRejected(
                "You are outside the outlet location. Move closer to check in."
            )
            msg.contains("mock location") -> CheckInState.Error(
                "Mock location provider detected. Please disable fake GPS apps."
            )
            code == 409 || (code == 422 && msg.contains("invalid_state_transition")) || msg.contains("conflict") || msg.contains("cannot transition") -> CheckInState.Conflict(
                "Visit status changed on server (e.g. marked missed). Please review schedule."
            )
            else -> CheckInState.Error(rawMessage)
        }
    }
}
