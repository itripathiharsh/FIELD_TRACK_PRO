package com.fieldtrackpro.android.data.api

import com.fieldtrackpro.android.data.model.DashboardSummaryDto
import com.fieldtrackpro.android.data.model.EmployeeDayDashboardDto
import retrofit2.Response
import retrofit2.http.GET
import retrofit2.http.Query

interface DashboardApi {
    @GET("api/v1/dashboard/summary")
    suspend fun getDashboardSummary(
        @Query("month") month: String? = "LIVE"
    ): Response<DashboardSummaryDto>

    @GET("api/v1/dashboard/my-day")
    suspend fun getMyDayDashboard(): Response<EmployeeDayDashboardDto>
}
