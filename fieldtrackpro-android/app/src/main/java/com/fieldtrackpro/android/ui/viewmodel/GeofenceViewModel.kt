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

enum class GeofenceUiStatus {
    UNKNOWN,
    LOCATING,
    INSIDE,
    OUTSIDE,
    GPS_UNAVAILABLE,
    PERMISSION_REQUIRED,
    LOCATION_NOT_CONFIGURED
}

/**
 * Represents the user's current geofence status.
 *
 * APP-ATT-005: Explicit state machine prevents check-in during unknown or unmonitored states.
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
    val status: GeofenceUiStatus = GeofenceUiStatus.UNKNOWN
) {
    /** True ONLY when actively monitoring and verified inside geofence radius. */
    val canProceedToCheckIn: Boolean
        get() = isMonitoring && isInside && !isLoadingLocation && hasPermission && isLocationEnabled
}

/**
 * ViewModel for managing geofence state for a visit.
 */
class GeofenceViewModel(application: Application) : AndroidViewModel(application) {

    private val geofenceManager = GeofenceManager(application)
    private val locationService = LocationCaptureService(application)

    private val _uiState = MutableStateFlow(GeofenceUiState())
    val uiState: StateFlow<GeofenceUiState> = _uiState.asStateFlow()

    private var currentGeofenceId: String? = null

    private val geofenceListener: (String, GeofenceState) -> Unit = { geofenceId, state ->
        if (geofenceId == currentGeofenceId) {
            val inside = state == GeofenceState.INSIDE
            _uiState.value = _uiState.value.copy(
                isInside = inside,
                isOutside = !inside,
                isMonitoring = true,
                status = if (inside) GeofenceUiStatus.INSIDE else GeofenceUiStatus.OUTSIDE
            )
        }
    }

    init {
        checkPermissions()
        GeofenceStateHolder.addListener(geofenceListener)
    }

    fun checkPermissions() {
        val hasPermission = locationService.hasFineLocationPermission()
        val isLocationEnabled = locationService.isLocationEnabled()
        val currentStatus = _uiState.value.status
        val newStatus = when {
            !hasPermission -> GeofenceUiStatus.PERMISSION_REQUIRED
            !isLocationEnabled -> GeofenceUiStatus.GPS_UNAVAILABLE
            currentStatus == GeofenceUiStatus.PERMISSION_REQUIRED || currentStatus == GeofenceUiStatus.GPS_UNAVAILABLE -> GeofenceUiStatus.LOCATING
            else -> currentStatus
        }
        _uiState.value = _uiState.value.copy(
            hasPermission = hasPermission,
            isLocationEnabled = isLocationEnabled,
            isInitialized = true,
            status = newStatus,
            errorMessage = if (hasPermission && isLocationEnabled && (_uiState.value.errorMessage?.contains("permission", ignoreCase = true) == true || _uiState.value.errorMessage?.contains("location", ignoreCase = true) == true)) null else _uiState.value.errorMessage
        )
    }

    /**
     * Called on Activity / Screen Resume to re-check location providers and re-trigger proximity detection.
     */
    fun onResume(customer: CustomerDto? = null, visitId: String? = null, radiusMeters: Float = 100f) {
        checkPermissions()
        val lat = customer?.latitude
        val lng = customer?.longitude
        if (lat != null && lng != null && geofenceManager.isValidCoordinate(lat, lng)) {
            val radiusD = customer.geofenceRadiusM?.toDouble() ?: radiusMeters.toDouble()
            if (locationService.isLocationEnabled() && locationService.hasFineLocationPermission()) {
                refreshRealtimeProximity(lat, lng, radiusD)
            }
        }
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

        if (lat == null || lng == null || !geofenceManager.isValidCoordinate(lat, lng)) {
            _uiState.value = _uiState.value.copy(
                errorMessage = "Customer location not configured",
                isInitialized = true,
                status = GeofenceUiStatus.LOCATION_NOT_CONFIGURED
            )
            return
        }

        val radiusD = radiusMeters.toDouble()

        if (currentGeofenceId == visitId && _uiState.value.isMonitoring) {
            refreshRealtimeProximity(lat, lng, radiusD)
            return
        }

        viewModelScope.launch {
            GeofenceManager.idToRemoveBeforeRegistering(currentGeofenceId, visitId)?.let {
                geofenceManager.removeGeofence(it)
            }

            currentGeofenceId = visitId

            _uiState.value = _uiState.value.copy(
                geofenceRadiusM = radiusD,
                isLoadingLocation = true,
                status = GeofenceUiStatus.LOCATING
            )

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
    }

    private fun refreshRealtimeProximity(targetLat: Double, targetLng: Double, radiusM: Double) {
        viewModelScope.launch {
            try {
                _uiState.value = _uiState.value.copy(isLoadingLocation = true, status = GeofenceUiStatus.LOCATING)
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
                    status = if (inside) GeofenceUiStatus.INSIDE else GeofenceUiStatus.OUTSIDE
                )
            } catch (e: LocationPermissionDeniedException) {
                _uiState.value = _uiState.value.copy(
                    hasPermission = false,
                    isLoadingLocation = false,
                    status = GeofenceUiStatus.PERMISSION_REQUIRED,
                    errorMessage = e.message
                )
            } catch (e: LocationServicesDisabledException) {
                _uiState.value = _uiState.value.copy(
                    isLocationEnabled = false,
                    isLoadingLocation = false,
                    status = GeofenceUiStatus.GPS_UNAVAILABLE,
                    errorMessage = e.message
                )
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(
                    isLoadingLocation = false,
                    status = GeofenceUiStatus.GPS_UNAVAILABLE,
                    errorMessage = e.message ?: "Unable to acquire fresh GPS fix",
                )
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
            status = GeofenceUiStatus.UNKNOWN
        )
    }

    override fun onCleared() {
        super.onCleared()
        GeofenceStateHolder.removeListener(geofenceListener)
        stopMonitoring()
    }
}
