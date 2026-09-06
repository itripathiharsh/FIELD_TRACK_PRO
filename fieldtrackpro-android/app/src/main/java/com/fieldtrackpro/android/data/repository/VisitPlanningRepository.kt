package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.VisitPlanningApi
import com.fieldtrackpro.android.data.model.EmployeeMonthlyAnalyticsDto
import com.fieldtrackpro.android.data.model.MonthlyVisitPlanDto
import com.fieldtrackpro.android.data.model.PlannedVisitCreateRequest
import com.fieldtrackpro.android.data.model.PlannedVisitDto
import com.fieldtrackpro.android.data.model.PlannedVisitRescheduleRequest
import com.fieldtrackpro.android.data.model.PlannedVisitUpdateRequest
import org.json.JSONObject
import retrofit2.Response

class VisitPlanningRepository(private val visitPlanningApi: VisitPlanningApi) {

    private fun <T> parseError(response: Response<T>, defaultMessage: String): String {
        return try {
            val errorBody = response.errorBody()?.string()
            if (!errorBody.isNullOrBlank()) {
                val json = JSONObject(errorBody)
                val detail = json.optString("detail", "")
                if (detail.isNotBlank()) detail else defaultMessage
            } else {
                defaultMessage
            }
        } catch (_: Exception) {
            defaultMessage
        }
    }

    suspend fun getMyPlan(year: Int? = null, month: Int? = null): Resource<MonthlyVisitPlanDto> {
        return try {
            val response = visitPlanningApi.getMyPlan(year = year, month = month)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                val errorMsg = parseError(response, "Failed to load monthly plan (${response.code()})")
                Resource.Error(errorMsg, response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage ?: "Unable to connect"}")
        }
    }

    suspend fun createPlannedVisit(request: PlannedVisitCreateRequest): Resource<PlannedVisitDto> {
        return try {
            val response = visitPlanningApi.createPlannedVisit(request)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                val errorMsg = parseError(response, "Failed to schedule visit (${response.code()})")
                Resource.Error(errorMsg, response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage ?: "Unable to connect"}")
        }
    }

    suspend fun updatePlannedVisit(id: String, request: PlannedVisitUpdateRequest): Resource<PlannedVisitDto> {
        return try {
            val response = visitPlanningApi.updatePlannedVisit(id, request)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                val errorMsg = parseError(response, "Failed to update visit (${response.code()})")
                Resource.Error(errorMsg, response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage ?: "Unable to connect"}")
        }
    }

    suspend fun reschedulePlannedVisit(id: String, newDate: String): Resource<PlannedVisitDto> {
        return try {
            val response = visitPlanningApi.reschedulePlannedVisit(id, PlannedVisitRescheduleRequest(newDate = newDate))
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                val errorMsg = parseError(response, "Failed to reschedule visit (${response.code()})")
                Resource.Error(errorMsg, response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage ?: "Unable to connect"}")
        }
    }

    suspend fun deletePlannedVisit(id: String): Resource<Unit> {
        return try {
            val response = visitPlanningApi.deletePlannedVisit(id)
            if (response.isSuccessful) {
                Resource.Success(Unit)
            } else {
                val errorMsg = parseError(response, "Failed to remove planned visit (${response.code()})")
                Resource.Error(errorMsg, response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage ?: "Unable to connect"}")
        }
    }

    suspend fun getMyMonthAnalytics(year: Int? = null, month: Int? = null): Resource<EmployeeMonthlyAnalyticsDto> {
        return try {
            val response = visitPlanningApi.getMyMonthAnalytics(year = year, month = month)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                val errorMsg = parseError(response, "Failed to load monthly analytics (${response.code()})")
                Resource.Error(errorMsg, response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage ?: "Unable to connect"}")
        }
    }
}
