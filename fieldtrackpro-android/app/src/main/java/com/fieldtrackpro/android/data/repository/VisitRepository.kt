package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.CustomerApi
import com.fieldtrackpro.android.data.api.DashboardApi
import com.fieldtrackpro.android.data.api.GeoApi
import com.fieldtrackpro.android.data.api.VisitApi
import com.fieldtrackpro.android.data.local.ConflictType
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.PendingAction
import com.fieldtrackpro.android.data.local.SyncConflict
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.AdHocVisitCreateRequest
import com.fieldtrackpro.android.data.model.CheckInRequest
import com.fieldtrackpro.android.data.model.CheckOutRequest
import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.data.model.DashboardSummaryDto
import com.fieldtrackpro.android.data.model.EmployeeDayDashboardDto
import com.fieldtrackpro.android.data.model.GeoVerificationLogDto
import com.fieldtrackpro.android.data.model.LocationVerifyRequest
import com.fieldtrackpro.android.data.model.LocationVerifyResponse
import com.fieldtrackpro.android.data.model.SyncResult
import com.fieldtrackpro.android.data.model.VisitDto
import com.fieldtrackpro.android.data.remote.ApiClient
import java.time.Instant
import java.util.UUID

/**
 * Visit repository for managing visit lifecycle, geo verification, offline sync, and dashboard summaries.
 *
 * APP-CUST-001 / APP-CUST-002: Eliminated N+1 sequential customer queries; VisitDto contains customer details inline.
 * APP-API-002: Offline queue pauses on 401 and preserves queued actions without deletion.
 * APP-NAV-003: Integrated backend dashboard summary aggregates.
 */
class VisitRepository(
    private val visitApi: VisitApi,
    private val customerApi: CustomerApi,
    private val geoApi: GeoApi,
    private val offlineQueueManager: OfflineQueueManager,
    private val dashboardApi: DashboardApi? = null,
    private val tokenManager: TokenManager? = null,
    private val workdayApi: com.fieldtrackpro.android.data.api.WorkdayApi? = null,
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
                Resource.Success(response.body()!!)
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
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Failed to fetch today's visits (${response.code()})", response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage ?: "Unable to connect"}")
        }
    }

    suspend fun createAdHocVisit(
        customerId: String,
        adhocReason: String,
        adhocNotes: String? = null,
        scheduledAt: String? = null,
        requiredFormId: String? = null
    ): Resource<VisitDto> {
        return try {
            val response = visitApi.createAdHocVisit(
                AdHocVisitCreateRequest(
                    customerId = customerId,
                    adhocReason = adhocReason,
                    adhocNotes = adhocNotes,
                    scheduledAt = scheduledAt,
                    requiredFormId = requiredFormId
                )
            )
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Failed to initiate ad-hoc visit (${response.code()})", response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage ?: "Unable to connect"}")
        }
    }

    suspend fun searchCustomers(
        query: String,
        skip: Int = 0,
        limit: Int = 50
    ): Resource<List<CustomerDto>> {
        return try {
            val response = customerApi.getCustomers(
                skip = skip,
                limit = limit,
                search = query.ifBlank { null }
            )
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Failed to search customers (${response.code()})", response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage ?: "Unable to connect"}")
        }
    }

    suspend fun getVisitById(visitId: String): Resource<VisitDto> {
        return try {
            val response = visitApi.getVisitById(visitId)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Visit not found (${response.code()})", response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage ?: "Unable to connect"}")
        }
    }

    suspend fun getDashboardSummary(): Resource<DashboardSummaryDto> {
        if (dashboardApi == null) return Resource.Error("Dashboard API not initialized")
        return try {
            val response = dashboardApi.getDashboardSummary(month = "LIVE")
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Failed to fetch dashboard summary (${response.code()})", response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage ?: "Unable to connect"}")
        }
    }

    suspend fun getMyDayDashboard(): Resource<EmployeeDayDashboardDto> {
        if (dashboardApi == null) return Resource.Error("Dashboard API not initialized")
        return try {
            val response = dashboardApi.getMyDayDashboard()
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Failed to fetch my day dashboard (${response.code()})", response.code())
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
        accuracyM: Double,
        isMock: Boolean = false,
        isOfflineMode: Boolean = false,
        skipEnqueueOnFailure: Boolean = false,
        idempotencyKey: String? = null,
    ): Resource<VisitDto> {
        val currentUserId = tokenManager?.getUserId()
        val key = idempotencyKey ?: UUID.randomUUID().toString()
        if (isOfflineMode) {
            offlineQueueManager.enqueueAction(
                PendingAction(
                    userId = currentUserId,
                    visitId = visitId,
                    actionType = "CHECK_IN",
                    latitude = latitude,
                    longitude = longitude,
                    timestamp = capturedAtMillis,
                    accuracyM = accuracyM,
                    isMockLocation = isMock
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
                idempotencyKey = key,
            )
            val response = visitApi.checkIn(visitId, req)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                val errBody = response.errorBody()?.string() ?: "Check-in failed"
                Resource.Error("Check-in rejected (${response.code()}): $errBody", response.code())
            }
        } catch (e: Exception) {
            if (!skipEnqueueOnFailure) {
                offlineQueueManager.enqueueAction(
                    PendingAction(
                        userId = currentUserId,
                        visitId = visitId,
                        actionType = "CHECK_IN",
                        latitude = latitude,
                        longitude = longitude,
                        timestamp = capturedAtMillis,
                        accuracyM = accuracyM,
                        isMockLocation = isMock
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
        accuracyM: Double,
        isMock: Boolean = false,
        notes: String? = null,
        isOfflineMode: Boolean = false,
        skipEnqueueOnFailure: Boolean = false,
        idempotencyKey: String? = null,
    ): Resource<VisitDto> {
        val currentUserId = tokenManager?.getUserId()
        val key = idempotencyKey ?: UUID.randomUUID().toString()
        if (isOfflineMode) {
            offlineQueueManager.enqueueAction(
                PendingAction(
                    userId = currentUserId,
                    visitId = visitId,
                    actionType = "CHECK_OUT",
                    latitude = latitude,
                    longitude = longitude,
                    timestamp = capturedAtMillis,
                    notes = notes,
                    accuracyM = accuracyM,
                    isMockLocation = isMock
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
                idempotencyKey = key,
                notes = notes,
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
                        userId = currentUserId,
                        visitId = visitId,
                        actionType = "CHECK_OUT",
                        latitude = latitude,
                        longitude = longitude,
                        timestamp = capturedAtMillis,
                        notes = notes,
                        accuracyM = accuracyM,
                        isMockLocation = isMock
                    )
                )
            }
            Resource.Error("Network error during check-out. Queued for offline sync.", isQueued = true)
        }
    }

    suspend fun verifyLocation(
        customerId: String,
        latitude: Double,
        longitude: Double,
        accuracyM: Double = 10.0,
        isMockLocation: Boolean = false
    ): Resource<LocationVerifyResponse> {
        return try {
            val req = LocationVerifyRequest(
                customerId = customerId,
                latitude = latitude,
                longitude = longitude,
                accuracyM = accuracyM,
                isMockLocation = isMockLocation
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
     * Sync offline queue with conflict detection and user isolation.
     *
     * APP-API-002:
     * - When a 401 is received, pauses sync immediately and leaves all queued actions intact.
     * - User Isolation: Actions belonging to a different user are skipped and preserved for when that user logs in.
     * - Returns a [SyncResult] containing synced count and detected conflicts.
     */
    suspend fun syncOfflineQueue(activeUserId: String? = tokenManager?.getUserId()): SyncResult {
        val effectiveUserId = activeUserId ?: tokenManager?.getUserId()
        if (effectiveUserId.isNullOrBlank()) {
            // Unauthenticated: cannot sync actions without an active user session
            return SyncResult(syncedCount = 0, conflicts = emptyList())
        }

        val queue = offlineQueueManager.getQueue()
        var syncedCount = 0
        val conflicts = mutableListOf<SyncConflict>()

        for (action in queue) {
            // User Isolation: If action is tagged with a userId that does NOT match the active session, skip it
            if (action.userId != null && action.userId != effectiveUserId) {
                continue
            }

            // Check current visit status before attempting sync (for visit-specific actions)
            if (action.actionType in listOf("CHECK_IN", "CHECK_OUT")) {
                val visitStatus = getVisitById(action.visitId)
                if (visitStatus is Resource.Error && visitStatus.code == 401) {
                    // 401 Auth expired: pause synchronization immediately without modifying queue
                    return SyncResult(syncedCount = syncedCount, conflicts = conflicts)
                }

                if (visitStatus is Resource.Success) {
                    val visit = visitStatus.data
                    val conflict = detectConflict(action, visit.status)
                    if (conflict != null) {
                        offlineQueueManager.saveConflict(conflict)
                        conflicts.add(conflict)
                        continue
                    }
                }
            }

            val res = when (action.actionType) {
                "START_DAY" -> {
                    val wApi = workdayApi ?: (tokenManager?.let { ApiClient.createWorkdayApi(it) })
                    if (wApi != null) {
                        val repo = WorkdayRepository(wApi, offlineQueueManager, tokenManager)
                        repo.startDay(
                            action.latitude, action.longitude,
                            accuracyM = action.accuracyM,
                            notes = action.notes,
                            capturedAtMillis = action.timestamp,
                            skipEnqueueOnFailure = true,
                        )
                    } else {
                        Resource.Error("Missing Workday API client")
                    }
                }
                "END_DAY" -> {
                    val wApi = workdayApi ?: (tokenManager?.let { ApiClient.createWorkdayApi(it) })
                    if (wApi != null) {
                        val repo = WorkdayRepository(wApi, offlineQueueManager, tokenManager)
                        repo.endDay(
                            action.latitude, action.longitude,
                            accuracyM = action.accuracyM,
                            notes = action.notes,
                            capturedAtMillis = action.timestamp,
                            skipEnqueueOnFailure = true,
                        )
                    } else {
                        Resource.Error("Missing Workday API client")
                    }
                }
                "CHECK_IN" -> {
                    checkIn(
                        action.visitId, action.latitude, action.longitude,
                        capturedAtMillis = action.timestamp,
                        accuracyM = action.accuracyM ?: 0.0,
                        isMock = action.isMockLocation,
                        isOfflineMode = false,
                        idempotencyKey = action.id,
                        skipEnqueueOnFailure = true,
                    )
                }
                else -> {
                    checkOut(
                        action.visitId, action.latitude, action.longitude,
                        capturedAtMillis = action.timestamp,
                        accuracyM = action.accuracyM ?: 0.0,
                        isMock = action.isMockLocation,
                        notes = action.notes,
                        isOfflineMode = false,
                        idempotencyKey = action.id,
                        skipEnqueueOnFailure = true,
                    )
                }
            }

            when (res) {
                is Resource.Success -> {
                    offlineQueueManager.removeAction(action.id)
                    syncedCount++
                }
                is Resource.Error -> {
                    if (res.code == 401) {
                        // 401 Auth expired: pause synchronization, preserve remaining queue items
                        return SyncResult(syncedCount = syncedCount, conflicts = conflicts)
                    }
                    val conflict = detectConflictFromError(action, res.message, res.code)
                    if (conflict != null) {
                        offlineQueueManager.saveConflict(conflict)
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
