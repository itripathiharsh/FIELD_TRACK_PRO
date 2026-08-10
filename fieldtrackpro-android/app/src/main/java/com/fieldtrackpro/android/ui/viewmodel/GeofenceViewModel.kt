package com.fieldtrackpro.android.ui.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.geofencing.GeofenceManager
import com.fieldtrackpro.android.geofencing.GeofenceState
import com.fieldtrackpro.android.geofencing.GeofenceStateHolder
import com.fieldtrackpro.android.services.LocationCaptureService
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Represents the user's current geofence status.
 */
data class GeofenceUiState(
    val isInitialized: Boolean = false,
    val isInside: Boolean = false,
    val isOutside: Boolean = false,
    val hasPermission: Boolean = false,
    val isLocationEnabled: Boolean = false,
    val isMonitoring: Boolean = false,
    val errorMessage: String? = null,
)

/**
 * ViewModel for managing geofence state for a visit.
 *
 * Coordinates:
 * - Location permissions
 * - Geofence registration
 * - Inside/outside state updates
 * - UI state for geofence status display
 */
class GeofenceViewModel(application: Application) : AndroidViewModel(application) {

    private val geofenceManager = GeofenceManager(application)
    private val locationService = LocationCaptureService(application)

    private val _uiState = MutableStateFlow(GeofenceUiState())
    val uiState: StateFlow<GeofenceUiState> = _uiState.asStateFlow()

    private var currentGeofenceId: String? = null

    private val geofenceListener: (String, GeofenceState) -> Unit = { geofenceId, state ->
        if (geofenceId == currentGeofenceId) {
            _uiState.value = _uiState.value.copy(
                isInside = state == GeofenceState.INSIDE,
                isOutside = state == GeofenceState.OUTSIDE,
                isMonitoring = true,
            )
        }
    }

    init {
        checkPermissions()
        GeofenceStateHolder.addListener(geofenceListener)
    }

    fun checkPermissions() {
        val hasPermission = locationService.hasLocationPermission()
        val isLocationEnabled = locationService.isLocationEnabled()
        _uiState.value = _uiState.value.copy(
            hasPermission = hasPermission,
            isLocationEnabled = isLocationEnabled,
            isInitialized = true,
        )
    }

    /**
     * Start monitoring a customer location with geofence.
     *
     * @param visitId The visit ID (used as geofence ID)
     * @param customer The customer data containing coordinates
     * @param radiusMeters The geofence radius (default 100m)
     */
    fun startMonitoring(
        visitId: String,
        customer: CustomerDto,
        radiusMeters: Float = 100f,
    ) {
        val lat = customer.latitude
        val lng = customer.longitude

        if (!geofenceManager.isValidCoordinate(lat, lng)) {
            _uiState.value = _uiState.value.copy(
                errorMessage = "Invalid customer coordinates",
                isInitialized = true,
            )
            return
        }

        currentGeofenceId = visitId

        // Register geofence
        val success = geofenceManager.registerGeofence(
            geofenceId = visitId,
            latitude = lat,
            longitude = lng,
            radiusMeters = radiusMeters,
        )

        if (success) {
            _uiState.value = _uiState.value.copy(
                isMonitoring = true,
                errorMessage = null,
            )
        } else {
            _uiState.value = _uiState.value.copy(
                errorMessage = "Failed to register geofence",
            )
        }
    }

    /**
     * Stop monitoring the current geofence.
     */
    fun stopMonitoring() {
        currentGeofenceId?.let { geofenceManager.removeGeofence(it) }
        currentGeofenceId = null
        _uiState.value = _uiState.value.copy(
            isInside = false,
            isOutside = false,
            isMonitoring = false,
        )
    }

    override fun onCleared() {
        super.onCleared()
        GeofenceStateHolder.removeListener(geofenceListener)
        stopMonitoring()
    }
}
