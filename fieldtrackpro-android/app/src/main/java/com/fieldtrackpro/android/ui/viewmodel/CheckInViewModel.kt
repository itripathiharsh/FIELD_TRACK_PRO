package com.fieldtrackpro.android.ui.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.api.VerificationRequestBody
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.LocationVerifyResponse
import com.fieldtrackpro.android.data.model.VisitDto
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.CustomerRepository
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.data.repository.VisitRepository
import com.fieldtrackpro.android.services.FixSelector
import com.fieldtrackpro.android.services.FusedFixCollector
import com.fieldtrackpro.android.services.LocationCaptureService
import com.fieldtrackpro.android.services.LocationResult
import com.fieldtrackpro.android.utils.CoordinateValidator
import com.fieldtrackpro.android.utils.GeoDecision
import com.fieldtrackpro.android.workers.OfflineSyncScheduler
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.time.Instant

sealed class CheckInState {
    object Idle : CheckInState()
    object Processing : CheckInState()

    /** Fresh fused fixes are being collected (up to 45 s). Values are the best fix seen so far. */
    data class Collecting(
        val elapsedS: Int,
        val bestAccuracyM: Double?,
        val distanceM: Double?,
        val outcome: GeoDecision.Outcome?
    ) : CheckInState()

    /** Still uncertain after the window and the point estimate is outside the radius: an admin can verify. */
    data class NeedsVerification(val distanceM: Double, val accuracyM: Double) : CheckInState()
    data class VerificationRequested(val message: String) : CheckInState()

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
 * Visit check-in with an accuracy-aware geofence decision (design-review/gps-checkin-decision-spec.md).
 *
 * Flow: collect fresh fused fixes for up to 45 s while evaluating each one against the outlet pin (INSIDE / OUTSIDE
 * stop the collection early), keep the best fix, then
 *   INSIDE                        -> submit
 *   UNCERTAIN, point inside       -> submit (the server records a conditional check-in flagged for admin review)
 *   UNCERTAIN, point outside      -> offer Request Admin Verification
 *   OUTSIDE                       -> show the distance, do not submit
 *   POOR_FIX / none               -> guidance, retry
 * The server re-decides every submission; no photo is ever needed.
 */
class CheckInViewModel(
    application: Application,
    private val tokenManager: TokenManager,
    offlineQueueManager: OfflineQueueManager
) : AndroidViewModel(application) {

    private val repository = VisitRepository(
        visitApi = ApiClient.createVisitApi(tokenManager),
        customerApi = ApiClient.createCustomerApi(tokenManager),
        geoApi = ApiClient.createGeoApi(tokenManager),
        offlineQueueManager = offlineQueueManager
    )
    private val customerRepository by lazy { CustomerRepository(ApiClient.createCustomerApi(tokenManager)) }
    private val reviewApi by lazy { ApiClient.createCheckInReviewApi(tokenManager) }

    private val _state = MutableStateFlow<CheckInState>(CheckInState.Idle)
    val state: StateFlow<CheckInState> = _state.asStateFlow()

    private var collectJob: Job? = null

    /** The fix the employee would ask an admin to verify (set when the result is uncertain and outside). */
    private var verificationFix: LocationResult? = null

    fun resetState() {
        collectJob?.cancel()
        _state.value = CheckInState.Idle
    }

    fun cancelCollection() {
        collectJob?.cancel()
        _state.value = CheckInState.Idle
    }

    /** Whole check-in: collect, decide, submit. [simulateOffline] is a debug-only QA switch. */
    fun startCheckIn(visitId: String, customerId: String, simulateOffline: Boolean = false) {
        if (_state.value is CheckInState.Collecting || _state.value is CheckInState.Processing) return
        verificationFix = null
        collectJob?.cancel()
        collectJob = viewModelScope.launch {
            val app = getApplication<Application>()
            val service = LocationCaptureService(app)
            if (!service.hasFineLocationPermission()) {
                _state.value = CheckInState.Error("Location permission is needed to check in. Allow precise location for FieldTrack in the app settings.")
                return@launch
            }
            if (!service.isLocationEnabled()) {
                _state.value = CheckInState.Error("Location is turned off. Turn on location to check in.")
                return@launch
            }
            _state.value = CheckInState.Collecting(0, null, null, null)

            val customer = (customerRepository.getCustomerById(customerId) as? Resource.Success)?.data
            val pinLat = customer?.latitude
            val pinLon = customer?.longitude
            if (customer == null) {
                _state.value = CheckInState.Error("Could not load the outlet details. Check your connection and try again.")
                return@launch
            }
            if (pinLat == null || pinLon == null) {
                _state.value = CheckInState.Error(NO_OUTLET_GPS)
                return@launch
            }
            val selector = FixSelector(pinLat, pinLon, customer.outletPinAccuracyM, customer.geofenceRadiusM.toDouble())
            val startedAt = System.currentTimeMillis()
            try {
                FusedFixCollector(app).collect(
                    maxMs = FusedFixCollector.MAX_WINDOW_MS,
                    onFix = { fix ->
                        val c = selector.offer(fix)
                        val best = selector.best
                        _state.value = CheckInState.Collecting(
                            elapsedS = ((System.currentTimeMillis() - startedAt) / 1000).toInt(),
                            bestAccuracyM = best?.fix?.accuracy?.toDouble()?.takeIf { it < 1e6 },
                            distanceM = best?.distanceM,
                            outcome = best?.decision?.outcome ?: c.decision.outcome
                        )
                    },
                    // INSIDE / OUTSIDE are conclusive; anything else keeps looking for a better fix.
                    stopWhen = { selector.latest?.conclusive == true && selector.latest?.fix === it }
                )
            } catch (e: SecurityException) {
                _state.value = CheckInState.Error("Location permission is needed to check in.")
                return@launch
            }
            decideAndSubmit(visitId, selector.best, simulateOffline)
        }
    }

    private suspend fun decideAndSubmit(visitId: String, best: FixSelector.Candidate?, simulateOffline: Boolean) {
        if (best == null || !best.decidable) {
            _state.value = CheckInState.LowAccuracy(poorFixMessage(best))
            return
        }
        val fix = best.fix
        if (fix.isMockLocation) {
            _state.value = CheckInState.Error("Mock location provider detected. Please disable fake GPS apps.")
            return
        }
        val d = best.distanceM.toInt()
        val acc = fix.accuracy.toInt()
        when (best.decision.outcome) {
            GeoDecision.Outcome.OUTSIDE -> {
                _state.value = CheckInState.GeoRejected("You are about $d m from the outlet (GPS ±$acc m), outside the allowed ${radiusText()}. Move closer to check in.")
            }
            GeoDecision.Outcome.UNCERTAIN -> {
                if (best.decision.pointInside) {
                    submit(visitId, fix, simulateOffline)
                } else {
                    verificationFix = fix
                    _state.value = CheckInState.NeedsVerification(best.distanceM, fix.accuracy.toDouble())
                }
            }
            GeoDecision.Outcome.INSIDE -> submit(visitId, fix, simulateOffline)
            GeoDecision.Outcome.POOR_FIX -> _state.value = CheckInState.LowAccuracy(poorFixMessage(best))
        }
    }

    private fun radiusText() = "outlet radius"

    private fun poorFixMessage(best: FixSelector.Candidate?): String = when (best?.decision?.reason) {
        "STALE" -> "The GPS reading is not fresh. Wait a few seconds and try again."
        "ACCURACY_UNKNOWN" -> "The phone did not report how accurate its GPS is. Try again in a moment."
        "ACCURACY_TOO_LOW" -> "GPS is too weak right now (±${best.fix.accuracy.toInt()} m). Move closer to the entrance or a window and try again."
        "INVALID_COORDINATES" -> "The phone returned an invalid location. Try again."
        else -> "No reliable GPS fix yet. Move closer to the entrance or a window and try again."
    }

    private suspend fun submit(visitId: String, fix: LocationResult, simulateOffline: Boolean) {
        _state.value = CheckInState.Processing
        when (
            val res = repository.checkIn(
                visitId, fix.latitude, fix.longitude,
                capturedAtMillis = fix.timestamp,
                accuracyM = fix.accuracy.toDouble(),
                isMock = fix.isMockLocation,
                isOfflineMode = simulateOffline,
            )
        ) {
            is Resource.Success -> _state.value = CheckInState.ActionSuccess(res.data, successMessage(res.data))
            is Resource.Error -> {
                if (res.isQueued) {
                    OfflineSyncScheduler.scheduleSync(getApplication())
                    _state.value = CheckInState.Queued(
                        "No connection. Your check-in is saved and will sync when the network returns. It will be marked for admin review because it was sent late."
                    )
                } else {
                    verificationFix = fix
                    _state.value = parseError(res.message, res.code, fix)
                }
            }
            else -> {}
        }
    }

    private fun successMessage(visit: VisitDto): String = when (visit.checkInConfidence) {
        "LOW" -> "Checked in. Your GPS was not precise enough to be certain, so an admin will review this check-in."
        "OFFLINE" -> "Checked in. Because it was sent late, an admin will review it."
        else -> "Check-in verified successfully!"
    }

    /** Asks an admin to verify the uncertain, outside-the-radius fix collected above. */
    fun requestVerification(visitId: String) {
        val fix = verificationFix ?: run {
            _state.value = CheckInState.Error("Take a fresh location first, then request verification.")
            return
        }
        if (_state.value is CheckInState.Processing) return
        viewModelScope.launch {
            _state.value = CheckInState.Processing
            try {
                val response = reviewApi.requestVerification(
                    VerificationRequestBody(
                        visitId = visitId,
                        latitude = fix.latitude,
                        longitude = fix.longitude,
                        accuracyM = fix.accuracy.toDouble(),
                        isMockLocation = fix.isMockLocation,
                        capturedAt = Instant.ofEpochMilli(fix.timestamp).toString()
                    )
                )
                if (response.isSuccessful) {
                    verificationFix = null
                    _state.value = CheckInState.VerificationRequested(
                        "Request sent. An administrator will review it and you will get a notification. You can keep trying to check in meanwhile."
                    )
                } else {
                    val raw = response.errorBody()?.string().orEmpty()
                    _state.value = CheckInState.Error(verificationErrorMessage(response.code(), raw))
                }
            } catch (e: Exception) {
                _state.value = CheckInState.Error("Could not send the request. Check your connection and try again.")
            }
        }
    }

    internal fun verificationErrorMessage(code: Int, raw: String): String {
        val msg = cleanServerMessage(raw)
        return when {
            code == 429 -> msg.ifBlank { "Too many verification requests. Please try again later." }
            code == 409 && raw.contains("VERIFICATION_ALREADY_PENDING") -> "A request for this visit is already waiting for an administrator."
            code == 409 && raw.contains("CHECKIN_ALLOWED") -> "Your location is good enough now. Press Check In."
            else -> msg.ifBlank { "The request could not be sent." }
        }
    }

    /** "Check-in rejected (422): {"error":{"message":"..."}}" -> just the server's message. */
    private fun cleanServerMessage(raw: String): String =
        Regex("\"message\"\\s*:\\s*\"([^\"]+)\"").find(raw)?.groupValues?.get(1)
            ?: Regex("\"detail\"\\s*:\\s*\"([^\"]+)\"").find(raw)?.groupValues?.get(1) ?: raw

    private fun parseError(rawMessage: String, code: Int?, fix: LocationResult?): CheckInState {
        val msg = rawMessage.lowercase()
        return when {
            msg.contains("geo_uncertain") || msg.contains("location is uncertain") -> {
                val d = Regex("about (\\d+)m").find(msg)?.groupValues?.get(1)?.toDoubleOrNull() ?: 0.0
                CheckInState.NeedsVerification(d, fix?.accuracy?.toDouble() ?: 0.0)
            }
            msg.contains("too old") || msg.contains("stale") -> CheckInState.StaleLocation(
                "The GPS reading was too old. Wait a few seconds for a fresh one and try again."
            )
            msg.contains("future") -> CheckInState.StaleLocation(
                "GPS timestamp is in the future. Please check device clock settings."
            )
            msg.contains("accuracy") || msg.contains("threshold") -> CheckInState.LowAccuracy(
                "GPS is too weak right now. Move closer to the entrance or a window and try again."
            )
            msg.contains("exceeds allowed radius") || msg.contains("outside") || msg.contains("geofence") -> CheckInState.GeoRejected(
                Regex("distance \\((\\d+(?:\\.\\d+)?)m\\)").find(msg)?.groupValues?.get(1)?.toDoubleOrNull()
                    ?.let { "You are about ${it.toInt()} m from the outlet, outside the allowed radius. Move closer to check in." }
                    ?: "You are outside the outlet location. Move closer to check in."
            )
            msg.contains("outlet_location_not_configured") || msg.contains("outlet location is not configured") -> CheckInState.Error(NO_OUTLET_GPS)
            msg.contains("mock location") -> CheckInState.Error(
                "Mock location provider detected. Please disable fake GPS apps."
            )
            code == 409 || (code == 422 && msg.contains("invalid_state_transition")) || msg.contains("conflict") || msg.contains("cannot transition") -> CheckInState.Conflict(
                "Visit status changed on server (e.g. marked missed). Please review schedule."
            )
            else -> CheckInState.Error(cleanServerMessage(rawMessage))
        }
    }

    // ---- kept for existing callers / tests ----

    fun verifyLocationPreflight(
        customerId: String,
        lat: Double?,
        lon: Double?,
        accuracyM: Double? = 10.0,
        isMock: Boolean = false
    ) {
        if (lat == null || lon == null || !CoordinateValidator.isValidCoordinate(lat, lon)) {
            _state.value = CheckInState.InvalidCoordinates("Invalid GPS coordinates. Please capture a fresh location fix.")
            return
        }
        viewModelScope.launch {
            _state.value = CheckInState.Processing
            when (val res = repository.verifyLocation(customerId, lat, lon, accuracyM ?: 10.0, isMock)) {
                is Resource.Success -> _state.value = CheckInState.VerifySuccess(res.data)
                is Resource.Error -> _state.value = parseError(res.message, res.code, null)
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
        if (lat == null || lon == null || !CoordinateValidator.isValidCoordinate(lat, lon)) {
            _state.value = CheckInState.InvalidCoordinates("Invalid GPS coordinates. Please capture a fresh location fix.")
            return
        }
        if (accuracyM == null || accuracyM < 0.0) {
            _state.value = CheckInState.LowAccuracy("Location accuracy unavailable. Please capture a fresh location fix.")
            return
        }
        viewModelScope.launch {
            submit(visitId, LocationResult(lat, lon, accuracyM.toFloat(), isMock, capturedAtMillis), isOfflineMode)
        }
    }

    private companion object {
        const val NO_OUTLET_GPS =
            "This outlet has no GPS location yet. Go back to the visit and tap Suggest Outlet Location while you are at the shop. Check-in itself needs no photo."
    }
}
