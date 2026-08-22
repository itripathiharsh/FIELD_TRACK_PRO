package com.fieldtrackpro.android

import android.app.Application
import android.util.Log
import com.fieldtrackpro.android.data.local.TokenManager
import com.google.firebase.messaging.FirebaseMessaging
import org.maplibre.android.MapLibre

class FieldTrackApp : Application() {
    override fun onCreate() {
        super.onCreate()
        try {
            MapLibre.getInstance(this)
        } catch (e: Exception) {
            e.printStackTrace()
        }

        // Initialize and cache FCM device token
        try {
            FirebaseMessaging.getInstance().token.addOnCompleteListener { task ->
                if (task.isSuccessful && !task.result.isNullOrBlank()) {
                    val token = task.result
                    Log.i("FieldTrackApp", "FCM token initialized: ${token.take(15)}...")
                    TokenManager(this).saveFcmToken(token)
                }
            }
        } catch (e: Exception) {
            Log.w("FieldTrackApp", "FirebaseMessaging not initialized: ${e.message}")
        }
    }
}

