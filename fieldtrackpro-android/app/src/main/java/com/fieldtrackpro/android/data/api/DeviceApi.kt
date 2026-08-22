package com.fieldtrackpro.android.data.api

import com.fieldtrackpro.android.data.model.DeviceDto
import com.fieldtrackpro.android.data.model.DeviceRegisterRequest
import com.fieldtrackpro.android.data.model.DeviceUnregisterRequest
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST

interface DeviceApi {
    @POST("api/v1/devices/register")
    suspend fun registerDevice(@Body request: DeviceRegisterRequest): Response<DeviceDto>

    @POST("api/v1/devices/unregister")
    suspend fun unregisterDevice(@Body request: DeviceUnregisterRequest): Response<Map<String, Any>>

    @GET("api/v1/devices/me")
    suspend fun getMyDevices(): Response<List<DeviceDto>>
}
