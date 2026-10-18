package com.fieldtrackpro.android

import android.app.Application
import android.util.Log
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.TokenManager
import com.google.firebase.messaging.FirebaseMessaging
import org.maplibre.android.MapLibre

class FieldTrackApp : Application() {
    override fun onCreate() {
        super.onCreate()
        try {
            MapLibre.getInstance(this)
        } catch (e: Exception) {
            Log.w("FieldTrackApp", "MapLibre init failed: ${e.javaClass.simpleName}")
        }

        // Keystore / EncryptedSharedPreferences opening and queue JSON parsing are slow disk + crypto work: they
        // no longer run inside Application.onCreate (which blocks process start). A background thread warms the
        // shared singletons (TokenManager, OfflineQueueManager - whose getInstance() also performs the one-time
        // legacy-queue attribution BEFORE publishing the instance, so no reader can observe the pre-migration queue).
        // The first screen still needs TokenManager to route (it waits on the same singleton lock), so this removes
        // the work from process start rather than from the critical path of the first frame.
        // Housekeeping (same thread): sweep abandoned outlet-proof photos (older than 7 days, referenced by no queue
        // entry, conflict or capture draft).
        Thread {
            try {
                TokenManager.getInstance(this)
                val manager = OfflineQueueManager.getInstance(this)
                val referenced = (manager.getQueue().map { it.outletProofPayload?.photoPath } +
                    manager.getConflicts().map { it.pendingAction.outletProofPayload?.photoPath } +
                    com.fieldtrackpro.android.data.local.OutletProofDraftStore.create(this).allPhotoPaths())
                    .filterNotNull().toSet()
                com.fieldtrackpro.android.data.local.OutletProofStore.pruneOrphaned(this, referenced)
            } catch (e: Exception) {
                Log.w("FieldTrackApp", "Outlet proof sweep skipped: ${e.javaClass.simpleName}")
            }
        }.start()

        // Initialize and cache FCM device token
        try {
            FirebaseMessaging.getInstance().token.addOnCompleteListener { task ->
                if (task.isSuccessful && !task.result.isNullOrBlank()) {
                    val token = task.result
                    if (BuildConfig.DEBUG) Log.d("FieldTrackApp", "FCM token initialized")
                    TokenManager.getInstance(this).saveFcmToken(token)
                }
            }
        } catch (e: Exception) {
            Log.w("FieldTrackApp", "FirebaseMessaging not initialized: ${e.message}")
        }
    }
}

