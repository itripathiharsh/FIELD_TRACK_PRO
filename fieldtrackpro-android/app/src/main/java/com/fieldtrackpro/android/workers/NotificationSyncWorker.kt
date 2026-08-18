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

class NotificationSyncWorker(
    private val context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    companion object {
        private const val TAG = "NotificationSyncWorker"
        private const val PREFS_NOTIF_TRACKER = "fieldtrack_notif_tracker"
        private const val KEY_DELIVERED_IDS = "delivered_notif_ids"
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
                    val prefs = context.getSharedPreferences(PREFS_NOTIF_TRACKER, Context.MODE_PRIVATE)
                    val deliveredIds = prefs.getStringSet(KEY_DELIVERED_IDS, emptySet())?.toMutableSet() ?: mutableSetOf()

                    for (notif in notifications) {
                        if (!notif.isRead && !deliveredIds.contains(notif.id)) {
                            val title = when (notif.notificationType) {
                                "NEW_VISIT" -> "New Visit Assigned"
                                "RESCHEDULED" -> "Visit Rescheduled"
                                "CANCELLED" -> "Visit Cancelled"
                                "REMINDER" -> "Visit Reminder"
                                else -> "FieldTrack Notification"
                            }

                            NotificationHelper.showNotification(
                                context = context,
                                notificationId = notif.id.hashCode(),
                                title = title,
                                message = notif.message,
                                visitId = notif.visitId
                            )
                            deliveredIds.add(notif.id)
                        }
                    }

                    prefs.edit().putStringSet(KEY_DELIVERED_IDS, deliveredIds).apply()
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
