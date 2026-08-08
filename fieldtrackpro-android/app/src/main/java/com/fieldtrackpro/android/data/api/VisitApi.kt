package com.fieldtrackpro.android.data.api

import com.fieldtrackpro.android.data.model.CheckInRequest
import com.fieldtrackpro.android.data.model.CheckOutRequest
import com.fieldtrackpro.android.data.model.GeoVerificationLogDto
import com.fieldtrackpro.android.data.model.VisitDto
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

interface VisitApi {
    @GET("api/v1/visits")
    suspend fun getVisits(
        @Query("status") status: String? = null
    ): Response<List<VisitDto>>

    @GET("api/v1/visits/{visit_id}")
    suspend fun getVisitById(
        @Path("visit_id") visitId: String
    ): Response<VisitDto>

    @POST("api/v1/visits/{visit_id}/check-in")
    suspend fun checkIn(
        @Path("visit_id") visitId: String,
        @Body request: CheckInRequest
    ): Response<VisitDto>

    @POST("api/v1/visits/{visit_id}/check-out")
    suspend fun checkOut(
        @Path("visit_id") visitId: String,
        @Body request: CheckOutRequest
    ): Response<VisitDto>

    @GET("api/v1/visits/{visit_id}/geo-logs")
    suspend fun getVisitGeoLogs(
        @Path("visit_id") visitId: String
    ): Response<List<GeoVerificationLogDto>>
}
