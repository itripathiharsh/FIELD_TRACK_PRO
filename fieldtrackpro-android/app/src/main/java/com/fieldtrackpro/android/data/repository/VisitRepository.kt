package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.CustomerApi
import com.fieldtrackpro.android.data.api.GeoApi
import com.fieldtrackpro.android.data.api.VisitApi
import com.fieldtrackpro.android.data.local.ConflictType
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.PendingAction
import com.fieldtrackpro.android.data.local.SyncConflict
import com.fieldtrackpro.android.data.model.CheckInRequest
import com.fieldtrackpro.android.data.model.CheckOutRequest
import com.fieldtrackpro.android.data.model.GeoVerificationLogDto
import com.fieldtrackpro.android.data.model.LocationVerifyRequest
import com.fieldtrackpro.android.data.model.LocationVerifyResponse
import com.fieldtrackpro.android.data.model.SyncResult
import com.fieldtrackpro.android.data.model.VisitDto
import java.time.Instant

class VisitRepository(
    private val visitApi: VisitApi,
    private val customerApi: CustomerApi,
    private val geoApi: GeoApi,
    private val offlineQueueManager: OfflineQueueManager
) {
    suspend fun getVisits(
        status: String? = null,
        search: String? = null,
        skip: Int = 0,
        limit: Int = 50
    ): Resource<List<VisitDto>> {
        return try {
            val response = visitApi.getVisits(
                status = status,
                search = search,
                skip = skip,
                limit = limit
            )
            if (response.isSuccessful && response.body() != null) {
                val rawVisits = response.body()!!
                // Enrich visit with customer name/address if available
                val enrichedVisits = rawVisits.map { visit ->
                    try {
                        val custResp = customerApi.getCustomerById(visit.customerId)
                        if (custResp.isSuccessful && custResp.body() != null) {
                            val cust = custResp.body()!!
                            visit.copy(customerName = cust.name, customerAddress = cust.address)
                        } else visit
                    } catch (e: Exception) {
                        visit
                    }
                }
                Resource.Success(enrichedVisits)
            } else {
                Resource.Error("Failed to fetch visits (${response.code()})", response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage ?: "Unable to connect"}")
        }
    }

    suspend fun getTodayVisits(
        status: String? = null,
        search: String? = null,
        skip: Int = 0,
        limit: Int = 50
    ): Resource<List<VisitDto>> {
        return try {
            val response = visitApi.getMyTodayVisits(
                status = status,
                search = search,
                skip = skip,
                limit = limit
            )
            if (response.isSuccessful && response.body() != null) {
                val rawVisits = response.body()!!
                val enrichedVisits = rawVisits.map { visit ->
                    try {
                        val custResp = customerApi.getCustomerById(visit.customerId)
                        if (custResp.isSuccessful && custResp.body() != null) {
                            val cust = custResp.body()!!
                            visit.copy(customerName = cust.name, customerAddress = cust.address)
                        } else visit
                    } catch (e: Exception) {
                        visit
                    }
                }
                Resource.Success(enrichedVisits)
            } else {
                Resource.Error("Failed to fetch today's visits (${response.code()})", response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage ?: "Unable to connect"}")
        }
    }

    suspend fun getVisitById(visitId: String): Resource<VisitDto> {
        return try {
            val response = visitApi.getVisitById(visitId)
            if (response.isSuccessful && response.body() != null) {
                var visit = response.body()!!
                try {
                    val custResp = customerApi.getCustomerById(visit.customerId)
                    if (custResp.isSuccessful && custResp.body() != null) {
                        val cust = custResp.body()!!
                        visit = visit.copy(customerName = cust.name, customerAddress = cust.address)
                    }
                } catch (e: Exception) {
                    // non-fatal customer detail enrichment
                }
                Resource.Success(visit)
            } else {
                Resource.Error("Visit not found (${response.code()})", response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage ?: "Unable to connect"}")
        }
    }

    suspend fun checkIn(
        visitId: String,
        latitude: Double,
        longitude: Double,
        capturedAtMillis: Long,
        accuracyM: Double? = 15.0,
        isMock: Boolean = false,
        isOfflineMode: Boolean = false,
        idempotencyKey: String? = null,
        skipEnqueueOnFailure: Boolean = false,
    ): Resource<VisitDto> {
        if (isOfflineMode) {
            offlineQueueManager.enqueueAction(
                PendingAction(
                    visitId = visitId,
                    actionType = "CHECK_IN",
                    latitude = latitude,
                    longitude = longitude,
                    timestamp = capturedAtMillis,
                )
            )
            return Resource.Error("Network offline. Action queued for sync.", isQueued = true)
        }

        return try {
            val req = CheckInRequest(
                latitude = latitude,
                longitude = longitude,
                accuracyM = accuracyM,
                isMockLocation = isMock,
                capturedAt = Instant.ofEpochMilli(capturedAtMillis).toString(),
                idempotencyKey = idempotencyKey,
            )
            val response = visitApi.checkIn(visitId, req)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                val errBody = response.errorBody()?.string() ?: "Check-in failed"
                Resource.Error("Check-in rejected (${response.code()}): $errBody", response.code())
            }
        } catch (e: Exception) {
            // Queue action automatically if network call fails - unless this
            // call is itself a retry of an already-queued action (see
            // syncOfflineQueue), in which case that action is still sitting
            // in the queue and re-enqueueing here would create a duplicate
            // that accumulates on every failed retry.
            if (!skipEnqueueOnFailure) {
                offlineQueueManager.enqueueAction(
                    PendingAction(
                        visitId = visitId,
                        actionType = "CHECK_IN",
                        latitude = latitude,
                        longitude = longitude,
                        timestamp = capturedAtMillis,
                    )
                )
            }
            Resource.Error("Network error during check-in. Queued for offline sync.", isQueued = true)
        }
    }

    suspend fun checkOut(
        visitId: String,
        latitude: Double,
        longitude: Double,
        capturedAtMillis: Long,
        accuracyM: Double? = 15.0,
        isMock: Boolean = false,
        notes: String? = null,
        isOfflineMode: Boolean = false,
        skipEnqueueOnFailure: Boolean = false,
        idempotencyKey: String? = null,
    ): Resource<VisitDto> {
        if (isOfflineMode) {
            offlineQueueManager.enqueueAction(
                PendingAction(
                    visitId = visitId,
                    actionType = "CHECK_OUT",
                    latitude = latitude,
                    longitude = longitude,
                    timestamp = capturedAtMillis,
                    notes = notes
                )
            )
            return Resource.Error("Network offline. Action queued for sync.", isQueued = true)
        }

        return try {
            val req = CheckOutRequest(
                latitude = latitude,
                longitude = longitude,
                accuracyM = accuracyM,
                isMockLocation = isMock,
                capturedAt = Instant.ofEpochMilli(capturedAtMillis).toString(),
                idempotencyKey = idempotencyKey,
            )
            val response = visitApi.checkOut(visitId, req)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                val errBody = response.errorBody()?.string() ?: "Check-out failed"
                Resource.Error("Check-out rejected (${response.code()}): $errBody", response.code())
            }
        } catch (e: Exception) {
            if (!skipEnqueueOnFailure) {
                offlineQueueManager.enqueueAction(
                    PendingAction(
                        visitId = visitId,
                        actionType = "CHECK_OUT",
                        latitude = latitude,
                        longitude = longitude,
                        timestamp = capturedAtMillis,
                        notes = notes
                    )
                )
            }
            Resource.Error("Network error during check-out. Queued for offline sync.", isQueued = true)
        }
    }

    suspend fun verifyLocation(customerId: String, latitude: Double, longitude: Double): Resource<LocationVerifyResponse> {
        return try {
            val req = LocationVerifyRequest(
                customerId = customerId,
                latitude = latitude,
                longitude = longitude
            )
            val response = geoApi.verifyLocation(req)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Location pre-check failed (${response.code()})", response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Location service error: ${e.localizedMessage}")
        }
    }

    suspend fun getVisitGeoLogs(visitId: String): Resource<List<GeoVerificationLogDto>> {
        return try {
            val response = visitApi.getVisitGeoLogs(visitId)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Failed to fetch geo logs (${response.code()})", response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    /**
     * Sync offline queue with conflict detection.
     *
     * Returns a [SyncResult] containing the number of successful syncs and
     * any conflicts that were detected.
     */
    suspend fun syncOfflineQueue(): SyncResult {
        val queue = offlineQueueManager.getQueue()
        var syncedCount = 0
        val conflicts = mutableListOf<SyncConflict>()

        for (action in queue) {
            // Check current visit status before attempting sync
            val visitStatus = getVisitById(action.visitId)
            if (visitStatus is Resource.Success) {
                val visit = visitStatus.data
                val conflict = detectConflict(action, visit.status)
                if (conflict != null) {
                    offlineQueueManager.addConflict(conflict)
                    conflicts.add(conflict)
                    continue
                }
            }

            // action.id is stable across retries of this same queued item, so
            // it doubles as the idempotency key: the backend enforces
            // uniqueness per visit on it, making a replayed check-in safe.
            // skipEnqueueOnFailure=true because `action` already represents
            // this pending work in the queue - re-enqueueing on a failed
            // retry would add a duplicate on top of the original.
            // action.timestamp is the ORIGINAL GPS capture time (see
            // PendingAction), not "now" - the server's freshness check must
            // see how old the fix genuinely was, not when this retry happened.
            val res = if (action.actionType == "CHECK_IN") {
                checkIn(
                    action.visitId, action.latitude, action.longitude,
                    capturedAtMillis = action.timestamp,
                    isOfflineMode = false,
                    idempotencyKey = action.id,
                    skipEnqueueOnFailure = true,
                )
            } else {
                checkOut(
                    action.visitId, action.latitude, action.longitude,
                    capturedAtMillis = action.timestamp,
                    notes = action.notes,
                    isOfflineMode = false,
                    idempotencyKey = action.id,
                    skipEnqueueOnFailure = true,
                )
            }

            when (res) {
                is Resource.Success -> {
                    offlineQueueManager.removeAction(action.id)
                    syncedCount++
                }
                is Resource.Error -> {
                    val conflict = detectConflictFromError(action, res.message, res.code)
                    if (conflict != null) {
                        offlineQueueManager.addConflict(conflict)
                        conflicts.add(conflict)
                    }
                }
                is Resource.Loading -> { /* no-op */ }
            }
        }

        return SyncResult(syncedCount = syncedCount, conflicts = conflicts)
    }

    private fun detectConflict(action: PendingAction, serverStatus: String?): SyncConflict? =
        Companion.detectConflict(action, serverStatus)

    private fun detectConflictFromError(action: PendingAction, errorMessage: String?, errorCode: Int?): SyncConflict? =
        Companion.detectConflictFromError(action, errorMessage, errorCode)

    companion object {
        /**
         * Pure conflict-detection logic, exposed here (rather than left as a
         * private instance method) specifically so tests can exercise the
         * real production logic directly instead of hand-copying a
         * duplicate of it - the ConflictDetectionTest.kt anti-pattern this
         * project has previously been criticized for.
         */
        fun detectConflict(action: PendingAction, serverStatus: String?): SyncConflict? {
            if (serverStatus == null) return null
            return when {
                action.actionType == "CHECK_IN" && serverStatus == "COMPLETED" -> SyncConflict(
                    pendingAction = action,
                    conflictType = ConflictType.STATUS_CHANGED,
                    serverStatus = serverStatus,
                    message = "Visit was already completed on server before check-in sync"
                )
                action.actionType == "CHECK_OUT" && serverStatus == "COMPLETED" -> SyncConflict(
                    pendingAction = action,
                    conflictType = ConflictType.STATUS_CHANGED,
                    serverStatus = serverStatus,
                    message = "Visit was already completed on server before check-out sync"
                )
                action.actionType == "CHECK_IN" && serverStatus == "MISSED" -> SyncConflict(
                    pendingAction = action,
                    conflictType = ConflictType.STATUS_CHANGED,
                    serverStatus = serverStatus,
                    message = "Visit was marked as missed on server"
                )
                action.actionType == "CHECK_OUT" && serverStatus == "PENDING" -> SyncConflict(
                    pendingAction = action,
                    conflictType = ConflictType.STATUS_CHANGED,
                    serverStatus = serverStatus,
                    message = "Cannot check out: visit has not been checked in"
                )
                else -> null
            }
        }

        fun detectConflictFromError(action: PendingAction, errorMessage: String?, errorCode: Int?): SyncConflict? {
            if (errorMessage == null) return null
            return when {
                // A queued action that, once finally synced, fails the server's
                // normal business rejection (outside geofence, stale fix, poor
                // accuracy, mock provider) - not a transport/auth problem, so it
                // must not just sit in the queue retrying forever with no
                // visibility; the rep needs to see and resolve this specifically.
                errorCode == 422 && errorMessage.contains("GEO_VERIFICATION_FAILED", ignoreCase = true) -> SyncConflict(
                    pendingAction = action,
                    conflictType = ConflictType.GEO_VALIDATION_FAILED,
                    serverStatus = null,
                    message = errorMessage
                )
                errorCode == 409 || errorMessage.contains("conflict", ignoreCase = true) -> SyncConflict(
                    pendingAction = action,
                    conflictType = ConflictType.SERVER_REJECTED,
                    serverStatus = null,
                    message = errorMessage
                )
                errorCode == 404 || errorMessage.contains("not found", ignoreCase = true) -> SyncConflict(
                    pendingAction = action,
                    conflictType = ConflictType.VISIT_UNAVAILABLE,
                    serverStatus = null,
                    message = errorMessage
                )
                errorCode != null && errorCode >= 500 -> SyncConflict(
                    pendingAction = action,
                    conflictType = ConflictType.NETWORK_ERROR,
                    serverStatus = null,
                    message = errorMessage
                )
                else -> null
            }
        }
    }
}


