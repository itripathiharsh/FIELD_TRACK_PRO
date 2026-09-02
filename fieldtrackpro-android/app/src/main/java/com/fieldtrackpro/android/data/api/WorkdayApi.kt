package com.fieldtrackpro.android.data.api

import com.fieldtrackpro.android.data.model.EmployeeWorkdayResponseDto
import com.fieldtrackpro.android.data.model.WorkSessionEndRequest
import com.fieldtrackpro.android.data.model.WorkSessionStartRequest
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Query

interface WorkdayApi {

    @POST("api/v1/workday/start")
    suspend fun startWorkday(
        @Body body: WorkSessionStartRequest
    ): Response<EmployeeWorkdayResponseDto>

    @POST("api/v1/workday/end")
    suspend fun endWorkday(
        @Body body: WorkSessionEndRequest
    ): Response<EmployeeWorkdayResponseDto>

    @GET("api/v1/workday/today")
    suspend fun getTodayWorkday(
        @Query("work_date") workDate: String? = null
    ): Response<EmployeeWorkdayResponseDto>
}
