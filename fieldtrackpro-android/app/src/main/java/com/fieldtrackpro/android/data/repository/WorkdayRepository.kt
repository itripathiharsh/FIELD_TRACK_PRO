package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.WorkdayApi
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.PendingAction
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.DailyFieldActivitySummaryDto
import com.fieldtrackpro.android.data.model.EmployeeWorkdayResponseDto
import com.fieldtrackpro.android.data.model.WorkSessionDto
import com.fieldtrackpro.android.data.model.WorkSessionEndRequest
import com.fieldtrackpro.android.data.model.WorkSessionStartRequest
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.UUID

class WorkdayRepository(
    private val workdayApi: WorkdayApi,
    private val offlineQueueManager: OfflineQueueManager? = null,
    private val tokenManager: TokenManager? = null,
) {

    private fun isoFormat(timestampMillis: Long = System.currentTimeMillis()): String {
        val sdf = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US)
        sdf.timeZone = TimeZone.getTimeZone("UTC")
        return sdf.format(Date(timestampMillis))
    }

    private fun todayDateString(): String {
        val sdf = SimpleDateFormat("yyyy-MM-dd", Locale.US)
        return sdf.format(Date())
    }

    suspend fun startDay(
        latitude: Double,
        longitude: Double,
        accuracyM: Double? = null,
        notes: String? = null,
        isOfflineMode: Boolean = false,
        capturedAtMillis: Long = System.currentTimeMillis(),
        skipEnqueueOnFailure: Boolean = false,
    ): Resource<EmployeeWorkdayResponseDto> {
        val isoTimestamp = isoFormat(capturedAtMillis)

        if (isOfflineMode) {
            if (!skipEnqueueOnFailure && offlineQueueManager != null) {
                val action = PendingAction(
                    userId = tokenManager?.getUserId(),
                    visitId = "workday",
                    actionType = "START_DAY",
                    latitude = latitude,
                    longitude = longitude,
                    timestamp = capturedAtMillis,
                    notes = notes,
                    accuracyM = accuracyM,
                )
                offlineQueueManager.enqueueAction(action)
            }
            return Resource.Success(
                EmployeeWorkdayResponseDto(
                    employeeId = tokenManager?.getUserId() ?: "",
                    workDate = todayDateString(),
                    session = WorkSessionDto(
                        id = UUID.randomUUID().toString(),
                        employeeId = tokenManager?.getUserId() ?: "",
                        workDate = todayDateString(),
                        status = "STARTED",
                        startTime = isoTimestamp,
                        startLatitude = latitude,
                        startLongitude = longitude,
                        startAccuracyMeters = accuracyM,
                        startNotes = notes,
                    ),
                    summary = DailyFieldActivitySummaryDto(workDate = todayDateString())
                )
            )
        }

        return try {
            val req = WorkSessionStartRequest(
                latitude = latitude,
                longitude = longitude,
                accuracyMeters = accuracyM,
                clientTimestamp = isoTimestamp,
                notes = notes,
            )
            val response = workdayApi.startWorkday(req)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                val errorBody = response.errorBody()?.string()
                val message = try {
                    val json = JSONObject(errorBody ?: "")
                    json.optJSONObject("error")?.optString("message")
                        ?: json.optString("detail", "Failed to start workday")
                } catch (e: Exception) {
                    "Failed to start workday (${response.code()})"
                }
                Resource.Error(message, response.code())
            }
        } catch (e: Exception) {
            if (!skipEnqueueOnFailure && offlineQueueManager != null) {
                val action = PendingAction(
                    userId = tokenManager?.getUserId(),
                    visitId = "workday",
                    actionType = "START_DAY",
                    latitude = latitude,
                    longitude = longitude,
                    timestamp = capturedAtMillis,
                    notes = notes,
                    accuracyM = accuracyM,
                )
                offlineQueueManager.enqueueAction(action)
                Resource.Success(
                    EmployeeWorkdayResponseDto(
                        employeeId = tokenManager?.getUserId() ?: "",
                        workDate = todayDateString(),
                        session = WorkSessionDto(
                            id = UUID.randomUUID().toString(),
                            employeeId = tokenManager?.getUserId() ?: "",
                            workDate = todayDateString(),
                            status = "STARTED",
                            startTime = isoTimestamp,
                            startLatitude = latitude,
                            startLongitude = longitude,
                            startAccuracyMeters = accuracyM,
                            startNotes = notes,
                        ),
                        summary = DailyFieldActivitySummaryDto(workDate = todayDateString())
                    )
                )
            } else {
                Resource.Error(e.localizedMessage ?: "Network error starting workday")
            }
        }
    }

    suspend fun endDay(
        latitude: Double,
        longitude: Double,
        accuracyM: Double? = null,
        notes: String? = null,
        isOfflineMode: Boolean = false,
        capturedAtMillis: Long = System.currentTimeMillis(),
        skipEnqueueOnFailure: Boolean = false,
    ): Resource<EmployeeWorkdayResponseDto> {
        val isoTimestamp = isoFormat(capturedAtMillis)

        if (isOfflineMode) {
            if (!skipEnqueueOnFailure && offlineQueueManager != null) {
                val action = PendingAction(
                    userId = tokenManager?.getUserId(),
                    visitId = "workday",
                    actionType = "END_DAY",
                    latitude = latitude,
                    longitude = longitude,
                    timestamp = capturedAtMillis,
                    notes = notes,
                    accuracyM = accuracyM,
                )
                offlineQueueManager.enqueueAction(action)
            }
            return Resource.Success(
                EmployeeWorkdayResponseDto(
                    employeeId = tokenManager?.getUserId() ?: "",
                    workDate = todayDateString(),
                    session = WorkSessionDto(
                        id = UUID.randomUUID().toString(),
                        employeeId = tokenManager?.getUserId() ?: "",
                        workDate = todayDateString(),
                        status = "COMPLETED",
                        endTime = isoTimestamp,
                        endLatitude = latitude,
                        endLongitude = longitude,
                        endAccuracyMeters = accuracyM,
                        endNotes = notes,
                    ),
                    summary = DailyFieldActivitySummaryDto(workDate = todayDateString())
                )
            )
        }

        return try {
            val req = WorkSessionEndRequest(
                latitude = latitude,
                longitude = longitude,
                accuracyMeters = accuracyM,
                clientTimestamp = isoTimestamp,
                notes = notes,
            )
            val response = workdayApi.endWorkday(req)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                val errorBody = response.errorBody()?.string()
                val message = try {
                    val json = JSONObject(errorBody ?: "")
                    json.optJSONObject("error")?.optString("message")
                        ?: json.optString("detail", "Failed to end workday")
                } catch (e: Exception) {
                    "Failed to end workday (${response.code()})"
                }
                Resource.Error(message, response.code())
            }
        } catch (e: Exception) {
            if (!skipEnqueueOnFailure && offlineQueueManager != null) {
                val action = PendingAction(
                    userId = tokenManager?.getUserId(),
                    visitId = "workday",
                    actionType = "END_DAY",
                    latitude = latitude,
                    longitude = longitude,
                    timestamp = capturedAtMillis,
                    notes = notes,
                    accuracyM = accuracyM,
                )
                offlineQueueManager.enqueueAction(action)
                Resource.Success(
                    EmployeeWorkdayResponseDto(
                        employeeId = tokenManager?.getUserId() ?: "",
                        workDate = todayDateString(),
                        session = WorkSessionDto(
                            id = UUID.randomUUID().toString(),
                            employeeId = tokenManager?.getUserId() ?: "",
                            workDate = todayDateString(),
                            status = "COMPLETED",
                            endTime = isoTimestamp,
                            endLatitude = latitude,
                            endLongitude = longitude,
                            endAccuracyMeters = accuracyM,
                            endNotes = notes,
                        ),
                        summary = DailyFieldActivitySummaryDto(workDate = todayDateString())
                    )
                )
            } else {
                Resource.Error(e.localizedMessage ?: "Network error ending workday")
            }
        }
    }

    suspend fun getTodayWorkday(workDate: String? = null): Resource<EmployeeWorkdayResponseDto> {
        return try {
            val response = workdayApi.getTodayWorkday(workDate)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Failed to load workday (${response.code()})", response.code())
            }
        } catch (e: Exception) {
            // Check if there are local queued actions for today
            val queued = offlineQueueManager?.getQueue() ?: emptyList()
            val endAction = queued.find { it.actionType == "END_DAY" }
            val startAction = queued.find { it.actionType == "START_DAY" }

            if (endAction != null) {
                Resource.Success(
                    EmployeeWorkdayResponseDto(
                        employeeId = tokenManager?.getUserId() ?: "",
                        workDate = todayDateString(),
                        session = WorkSessionDto(
                            id = endAction.id,
                            employeeId = tokenManager?.getUserId() ?: "",
                            workDate = todayDateString(),
                            status = "COMPLETED",
                            startTime = startAction?.let { isoFormat(it.timestamp) },
                            startLatitude = startAction?.latitude,
                            startLongitude = startAction?.longitude,
                            endTime = isoFormat(endAction.timestamp),
                            endLatitude = endAction.latitude,
                            endLongitude = endAction.longitude,
                            endAccuracyMeters = endAction.accuracyM,
                            endNotes = endAction.notes,
                        ),
                        summary = DailyFieldActivitySummaryDto(workDate = todayDateString())
                    )
                )
            } else if (startAction != null) {
                Resource.Success(
                    EmployeeWorkdayResponseDto(
                        employeeId = tokenManager?.getUserId() ?: "",
                        workDate = todayDateString(),
                        session = WorkSessionDto(
                            id = startAction.id,
                            employeeId = tokenManager?.getUserId() ?: "",
                            workDate = todayDateString(),
                            status = "STARTED",
                            startTime = isoFormat(startAction.timestamp),
                            startLatitude = startAction.latitude,
                            startLongitude = startAction.longitude,
                            startAccuracyMeters = startAction.accuracyM,
                            startNotes = startAction.notes,
                        ),
                        summary = DailyFieldActivitySummaryDto(workDate = todayDateString())
                    )
                )
            } else {
                Resource.Error(e.localizedMessage ?: "Failed to load workday")
            }
        }
    }
}
