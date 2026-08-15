package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.NotificationApi
import com.fieldtrackpro.android.data.model.NotificationDto

class NotificationRepository(private val notificationApi: NotificationApi) {

    suspend fun getMyNotifications(): Resource<List<NotificationDto>> {
        return try {
            val response = notificationApi.getMyNotifications()
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Failed to load notifications (${response.code()})")
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    suspend fun markAsRead(notificationId: String): Resource<Unit> {
        return try {
            val response = notificationApi.markAsRead(notificationId)
            if (response.isSuccessful) {
                Resource.Success(Unit)
            } else {
                Resource.Error("Failed to mark as read (${response.code()})")
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }
}
