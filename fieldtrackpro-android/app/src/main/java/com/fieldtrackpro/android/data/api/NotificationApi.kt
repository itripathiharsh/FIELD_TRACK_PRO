package com.fieldtrackpro.android.data.api

import com.fieldtrackpro.android.data.model.NotificationDto
import retrofit2.Response
import retrofit2.http.GET
import retrofit2.http.PATCH
import retrofit2.http.Path

interface NotificationApi {
    @GET("api/v1/notifications/me")
    suspend fun getMyNotifications(): Response<List<NotificationDto>>

    @PATCH("api/v1/notifications/{notification_id}/read")
    suspend fun markAsRead(
        @Path("notification_id") notificationId: String
    ): Response<Map<String, String>>
}
