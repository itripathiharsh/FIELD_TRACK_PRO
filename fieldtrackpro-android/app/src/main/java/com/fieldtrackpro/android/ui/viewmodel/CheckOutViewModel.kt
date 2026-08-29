package com.fieldtrackpro.android.ui.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.TokenManager
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

sealed class CheckOutState {
    object Idle : CheckOutState()
    object Processing : CheckOutState()
    data class ActionSuccess(val visit: VisitDto, val message: String) : CheckOutState()
    data class Queued(val message: String) : CheckOutState()
    data class GeoRejected(val message: String) : CheckOutState()
    data class LowAccuracy(val message: String) : CheckOutState()
    data class StaleLocation(val message: String) : CheckOutState()
    data class InvalidCoordinates(val message: String) : CheckOutState()
    data class Conflict(val message: String) : CheckOutState()
    data class Error(val message: String) : CheckOutState()
}

/**
 * Isolated ViewModel for Visit Check-Out.
 *
 * APP-ATT-001: Separate ViewModel/state holder so CheckOutScreen does not reset CheckInState.
 * APP-ATT-004: Validates GPS coordinates before dispatch; rejects (0,0) and invalid ranges.
 */
class CheckOutViewModel(
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

    private val _state = MutableStateFlow<CheckOutState>(CheckOutState.Idle)
    val state: StateFlow<CheckOutState> = _state.asStateFlow()

    fun resetState() {
        _state.value = CheckOutState.Idle
    }

    fun executeCheckOut(
        visitId: String,
        lat: Double?,
        lon: Double?,
        notes: String?,
        capturedAtMillis: Long,
        accuracyM: Double? = null,
        isMock: Boolean = false,
        isOfflineMode: Boolean = false,
    ) {
        if (!CoordinateValidator.isValidCoordinate(lat, lon)) {
            _state.value = CheckOutState.InvalidCoordinates(
                "Invalid GPS coordinates. Please capture a fresh location fix."
            )
            return
        }

        if (accuracyM == null || accuracyM < 0.0) {
            _state.value = CheckOutState.LowAccuracy(
                "Location accuracy unavailable. Please capture a fresh location fix."
            )
            return
        }

        viewModelScope.launch {
            _state.value = CheckOutState.Processing
            when (
                val res = repository.checkOut(
                    visitId, lat!!, lon!!,
                    capturedAtMillis = capturedAtMillis,
                    accuracyM = accuracyM,
                    isMock = isMock,
                    notes = notes,
                    isOfflineMode = isOfflineMode,
                )
            ) {
                is Resource.Success -> _state.value = CheckOutState.ActionSuccess(res.data, "Check-out verified. Visit completed!")
                is Resource.Error -> {
                    if (res.isQueued) {
                        OfflineSyncScheduler.scheduleSync(getApplication())
                        _state.value = CheckOutState.Queued("Check-out saved. It will sync automatically when network returns.")
                    } else {
                        _state.value = parseError(res.message, res.code)
                    }
                }
                else -> {}
            }
        }
    }

    private fun parseError(rawMessage: String, code: Int?): CheckOutState {
        val msg = rawMessage.lowercase()
        return when {
            msg.contains("too old") || msg.contains("stale") -> CheckOutState.StaleLocation(
                "GPS reading is older than 24 hours. Please capture a fresh location."
            )
            msg.contains("future") -> CheckOutState.StaleLocation(
                "GPS timestamp is in the future. Please check device clock settings."
            )
            msg.contains("accuracy") || msg.contains("threshold") -> CheckOutState.LowAccuracy(
                "Location accuracy is too low. Move to an open area and try again."
            )
            msg.contains("exceeds allowed radius") || msg.contains("outside") || msg.contains("geofence") -> CheckOutState.GeoRejected(
                "You are outside the outlet location. Move closer to check out."
            )
            msg.contains("mock location") -> CheckOutState.Error(
                "Mock location provider detected. Please disable fake GPS apps."
            )
            code == 409 || (code == 422 && msg.contains("invalid_state_transition")) || msg.contains("conflict") || msg.contains("cannot transition") -> CheckOutState.Conflict(
                "Visit status changed on server (e.g. already completed or missed)."
            )
            else -> CheckOutState.Error(rawMessage)
        }
    }
}
