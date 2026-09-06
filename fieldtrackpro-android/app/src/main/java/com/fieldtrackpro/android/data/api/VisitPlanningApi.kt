package com.fieldtrackpro.android.data.api

import com.fieldtrackpro.android.data.model.EmployeeMonthlyAnalyticsDto
import com.fieldtrackpro.android.data.model.MonthlyVisitPlanDto
import com.fieldtrackpro.android.data.model.PlannedVisitCreateRequest
import com.fieldtrackpro.android.data.model.PlannedVisitDto
import com.fieldtrackpro.android.data.model.PlannedVisitRescheduleRequest
import com.fieldtrackpro.android.data.model.PlannedVisitUpdateRequest
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

interface VisitPlanningApi {

    @GET("api/v1/visit-planning/my-plan")
    suspend fun getMyPlan(
        @Query("year") year: Int? = null,
        @Query("month") month: Int? = null
    ): Response<MonthlyVisitPlanDto>

    @POST("api/v1/visit-planning/visits")
    suspend fun createPlannedVisit(
        @Body request: PlannedVisitCreateRequest
    ): Response<PlannedVisitDto>

    @PATCH("api/v1/visit-planning/visits/{id}")
    suspend fun updatePlannedVisit(
        @Path("id") id: String,
        @Body request: PlannedVisitUpdateRequest
    ): Response<PlannedVisitDto>

    @POST("api/v1/visit-planning/visits/{id}/reschedule")
    suspend fun reschedulePlannedVisit(
        @Path("id") id: String,
        @Body request: PlannedVisitRescheduleRequest
    ): Response<PlannedVisitDto>

    @DELETE("api/v1/visit-planning/visits/{id}")
    suspend fun deletePlannedVisit(
        @Path("id") id: String
    ): Response<Unit>

    @GET("api/v1/visit-planning/analytics/my-month")
    suspend fun getMyMonthAnalytics(
        @Query("year") year: Int? = null,
        @Query("month") month: Int? = null
    ): Response<EmployeeMonthlyAnalyticsDto>
}
