package com.fieldtrackpro.android.ui.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.geofencing.GeofenceManager
import com.fieldtrackpro.android.geofencing.GeofenceState
import com.fieldtrackpro.android.geofencing.GeofenceStateHolder
import com.fieldtrackpro.android.services.LocationCaptureService
import com.fieldtrackpro.android.services.LocationPermissionDeniedException
import com.fieldtrackpro.android.services.LocationServicesDisabledException
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
    val isLoadingLocation: Boolean = false,
    val distanceM: Double? = null,
    val geofenceRadiusM: Double? = null,
    val accuracyM: Double? = null,
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
     * Start monitoring a customer location with geofence and active distance calculation.
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
        checkPermissions()
        val lat = customer.latitude
        val lng = customer.longitude

        if (!geofenceManager.isValidCoordinate(lat, lng)) {
            _uiState.value = _uiState.value.copy(
                errorMessage = "Invalid customer coordinates",
                isInitialized = true,
            )
            return
        }

        val radiusD = radiusMeters.toDouble()

        if (currentGeofenceId == visitId && _uiState.value.isMonitoring) {
            // Already monitoring, but refresh real-time distance
            refreshRealtimeProximity(lat, lng, radiusD)
            return
        }

        GeofenceManager.idToRemoveBeforeRegistering(currentGeofenceId, visitId)?.let {
            geofenceManager.removeGeofence(it)
        }

        currentGeofenceId = visitId

        val success = geofenceManager.registerGeofence(
            geofenceId = visitId,
            latitude = lat,
            longitude = lng,
            radiusMeters = radiusMeters,
        )

        _uiState.value = _uiState.value.copy(
            isMonitoring = success,
            geofenceRadiusM = radiusD,
            isLoadingLocation = true,
            errorMessage = if (success) null else "Could not register background geofence",
        )

        refreshRealtimeProximity(lat, lng, radiusD)
    }

    private fun refreshRealtimeProximity(targetLat: Double, targetLng: Double, radiusM: Double) {
        viewModelScope.launch {
            try {
                _uiState.value = _uiState.value.copy(isLoadingLocation = true)
                val loc = locationService.getCurrentLocation()
                val dist = LocationCaptureService.calculateDistanceM(
                    loc.latitude, loc.longitude, targetLat, targetLng
                )
                val inside = dist <= radiusM
                _uiState.value = _uiState.value.copy(
                    isInside = inside,
                    isOutside = !inside,
                    distanceM = dist,
                    geofenceRadiusM = radiusM,
                    accuracyM = loc.accuracy.toDouble(),
                    isLoadingLocation = false,
                    isLocationEnabled = true,
                    hasPermission = true,
                    errorMessage = null,
                )
            } catch (e: LocationPermissionDeniedException) {
                _uiState.value = _uiState.value.copy(
                    hasPermission = false,
                    isLoadingLocation = false,
                )
            } catch (e: LocationServicesDisabledException) {
                _uiState.value = _uiState.value.copy(
                    isLocationEnabled = false,
                    isLoadingLocation = false,
                )
            } catch (e: Exception) {
                // If fine location fails, try last known location fallback
                val last = locationService.getLastLocation()
                if (last != null) {
                    val dist = LocationCaptureService.calculateDistanceM(
                        last.latitude, last.longitude, targetLat, targetLng
                    )
                    val inside = dist <= radiusM
                    _uiState.value = _uiState.value.copy(
                        isInside = inside,
                        isOutside = !inside,
                        distanceM = dist,
                        geofenceRadiusM = radiusM,
                        accuracyM = last.accuracy.toDouble(),
                        isLoadingLocation = false,
                        errorMessage = null,
                    )
                } else {
                    _uiState.value = _uiState.value.copy(
                        isLoadingLocation = false,
                        errorMessage = e.message ?: "Unable to read current GPS location",
                    )
                }
            }
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
            distanceM = null,
            geofenceRadiusM = null,
        )
    }

    override fun onCleared() {
        super.onCleared()
        GeofenceStateHolder.removeListener(geofenceListener)
        stopMonitoring()
    }
}
