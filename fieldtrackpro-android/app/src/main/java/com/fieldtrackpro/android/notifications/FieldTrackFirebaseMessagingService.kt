package com.fieldtrackpro.android.notifications

import android.util.Log
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.DeviceRegisterRequest
import com.fieldtrackpro.android.data.remote.ApiClient
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * Firebase Cloud Messaging Service for FieldTrack Pro.
 * Handles incoming push notifications across foreground, background, and terminated states,
 * and handles FCM token refreshes.
 */
class FieldTrackFirebaseMessagingService : FirebaseMessagingService() {

    companion object {
        private const val TAG = "FieldTrackFCM"
    }

    override fun onNewToken(token: String) {
        super.onNewToken(token)
        Log.i(TAG, "New FCM token received: ${token.take(15)}...")

        val tokenManager = TokenManager(applicationContext)
        tokenManager.saveFcmToken(token)

        // If user is currently signed in, register the new token with the backend immediately
        if (tokenManager.isLoggedIn()) {
            CoroutineScope(Dispatchers.IO).launch {
                try {
                    val deviceApi = ApiClient.createDeviceApi(tokenManager)
                    val response = deviceApi.registerDevice(
                        DeviceRegisterRequest(
                            fcmToken = token,
                            deviceType = "ANDROID"
                        )
                    )
                    if (response.isSuccessful) {
                        Log.i(TAG, "FCM token successfully registered with backend")
                    } else {
                        Log.w(TAG, "Failed to register FCM token with backend: code=${response.code()}")
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "Error registering FCM token with backend", e)
                }
            }
        }
    }

    override fun onMessageReceived(remoteMessage: RemoteMessage) {
        super.onMessageReceived(remoteMessage)
        Log.d(TAG, "FCM message received from: ${remoteMessage.from}")

        val data = remoteMessage.data
        val notificationId = data["notification_id"]
            ?: remoteMessage.messageId
            ?: System.currentTimeMillis().toString()

        // Deduplication: prevent duplicate alerts if already received / displayed
        if (NotificationTracker.isDelivered(applicationContext, notificationId)) {
            Log.d(TAG, "Notification $notificationId already delivered; skipping duplicate.")
            return
        }

        val type = data["type"] ?: "NEW_VISIT"
        val fallbackTitle = when (type) {
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

        val title = data["title"] ?: remoteMessage.notification?.title ?: fallbackTitle
        val message = data["message"] ?: data["body"] ?: remoteMessage.notification?.body ?: ""
        val visitId = data["visit_id"]?.ifBlank { null }

        // Mark as delivered in shared tracker
        NotificationTracker.markDelivered(applicationContext, notificationId)

        // Show local heads-up notification
        NotificationHelper.showNotification(
            context = applicationContext,
            notificationId = notificationId.hashCode(),
            title = title,
            message = message,
            visitId = visitId,
            notificationIdStr = notificationId
        )
    }
}
