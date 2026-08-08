package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.CustomerApi
import com.fieldtrackpro.android.data.api.GeoApi
import com.fieldtrackpro.android.data.api.VisitApi
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.PendingAction
import com.fieldtrackpro.android.data.model.CheckInRequest
import com.fieldtrackpro.android.data.model.CheckOutRequest
import com.fieldtrackpro.android.data.model.GeoVerificationLogDto
import com.fieldtrackpro.android.data.model.LocationVerifyRequest
import com.fieldtrackpro.android.data.model.LocationVerifyResponse
import com.fieldtrackpro.android.data.model.VisitDto

class VisitRepository(
    private val visitApi: VisitApi,
    private val customerApi: CustomerApi,
    private val geoApi: GeoApi,
    private val offlineQueueManager: OfflineQueueManager
) {
    suspend fun getVisits(status: String? = null): Resource<List<VisitDto>> {
        return try {
            val response = visitApi.getVisits(status)
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
        accuracyM: Double? = 15.0,
        isMock: Boolean = false,
        isOfflineMode: Boolean = false
    ): Resource<VisitDto> {
        if (isOfflineMode) {
            offlineQueueManager.enqueueAction(
                PendingAction(
                    visitId = visitId,
                    actionType = "CHECK_IN",
                    latitude = latitude,
                    longitude = longitude
                )
            )
            return Resource.Error("Network offline. Action queued for sync.")
        }

        return try {
            val req = CheckInRequest(
                latitude = latitude,
                longitude = longitude,
                accuracyM = accuracyM,
                isMockLocation = isMock
            )
            val response = visitApi.checkIn(visitId, req)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                val errBody = response.errorBody()?.string() ?: "Check-in failed"
                Resource.Error("Check-in rejected (${response.code()}): $errBody", response.code())
            }
        } catch (e: Exception) {
            // Queue action automatically if network call fails
            offlineQueueManager.enqueueAction(
                PendingAction(
                    visitId = visitId,
                    actionType = "CHECK_IN",
                    latitude = latitude,
                    longitude = longitude
                )
            )
            Resource.Error("Network error during check-in. Queued for offline sync.")
        }
    }

    suspend fun checkOut(
        visitId: String,
        latitude: Double,
        longitude: Double,
        accuracyM: Double? = 15.0,
        isMock: Boolean = false,
        notes: String? = null,
        isOfflineMode: Boolean = false
    ): Resource<VisitDto> {
        if (isOfflineMode) {
            offlineQueueManager.enqueueAction(
                PendingAction(
                    visitId = visitId,
                    actionType = "CHECK_OUT",
                    latitude = latitude,
                    longitude = longitude,
                    notes = notes
                )
            )
            return Resource.Error("Network offline. Action queued for sync.")
        }

        return try {
            val req = CheckOutRequest(
                latitude = latitude,
                longitude = longitude,
                accuracyM = accuracyM,
                isMockLocation = isMock
            )
            val response = visitApi.checkOut(visitId, req)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                val errBody = response.errorBody()?.string() ?: "Check-out failed"
                Resource.Error("Check-out rejected (${response.code()}): $errBody", response.code())
            }
        } catch (e: Exception) {
            offlineQueueManager.enqueueAction(
                PendingAction(
                    visitId = visitId,
                    actionType = "CHECK_OUT",
                    latitude = latitude,
                    longitude = longitude,
                    notes = notes
                )
            )
            Resource.Error("Network error during check-out. Queued for offline sync.")
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

    suspend fun syncOfflineQueue(): Int {
        val queue = offlineQueueManager.getQueue()
        var syncedCount = 0
        for (action in queue) {
            val res = if (action.actionType == "CHECK_IN") {
                checkIn(action.visitId, action.latitude, action.longitude, isOfflineMode = false)
            } else {
                checkOut(action.visitId, action.latitude, action.longitude, notes = action.notes, isOfflineMode = false)
            }
            if (res is Resource.Success) {
                offlineQueueManager.removeAction(action.id)
                syncedCount++
            }
        }
        return syncedCount
    }
}
