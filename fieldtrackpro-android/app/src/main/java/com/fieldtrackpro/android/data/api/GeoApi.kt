package com.fieldtrackpro.android.data.api

import com.fieldtrackpro.android.data.model.LocationVerifyRequest
import com.fieldtrackpro.android.data.model.LocationVerifyResponse
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.POST

interface GeoApi {
    @POST("api/v1/geo/verify-location")
    suspend fun verifyLocation(
        @Body request: LocationVerifyRequest
    ): Response<LocationVerifyResponse>
}
