package com.fieldtrackpro.android.workers

import android.content.Context
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.NotificationRepository
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.notifications.NotificationHelper
import com.fieldtrackpro.android.notifications.NotificationTracker

class NotificationSyncWorker(
    private val context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    companion object {
        private const val TAG = "NotificationSyncWorker"
    }

    override suspend fun doWork(): Result {
        val tokenManager = TokenManager(context)
        if (!tokenManager.isLoggedIn()) {
            return Result.success()
        }

        val api = ApiClient.createNotificationApi(tokenManager)
        val repo = NotificationRepository(api)

        return try {
            when (val res = repo.getMyNotifications()) {
                is Resource.Success -> {
                    val notifications = res.data

                    for (notif in notifications) {
                        if (!notif.isRead && !NotificationTracker.isDelivered(context, notif.id)) {
                            val title = when (notif.notificationType) {
                                "NEW_VISIT" -> "New Visit Assigned"
                                "RESCHEDULED" -> "Visit Rescheduled"
                                "CANCELLED" -> "Visit Cancelled"
                                "REMINDER" -> "Visit Reminder"
                                "OVERDUE" -> "Visit Overdue"
                                "COMPLETED" -> "Visit Completed"
                                "GEO_FAILURE_ALERT" -> "Geofence Verification Alert"
                                "GEO_ALERT" -> "Geofence Alert"
                                else -> "FieldTrack Notification"
                            }

                            NotificationHelper.showNotification(
                                context = context,
                                notificationId = notif.id.hashCode(),
                                title = title,
                                message = notif.message,
                                visitId = notif.visitId,
                                notificationIdStr = notif.id
                            )
                            NotificationTracker.markDelivered(context, notif.id)
                        }
                    }

                    Result.success()
                }
                else -> Result.retry()
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to sync notifications", e)
            Result.retry()
        }
    }
}

