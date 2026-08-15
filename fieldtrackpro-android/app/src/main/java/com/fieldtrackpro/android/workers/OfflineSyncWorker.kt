package com.fieldtrackpro.android.workers

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.VisitRepository

/**
 * Runs the offline check-in/check-out queue the moment the device has
 * connectivity again, instead of requiring the rep to remember to open the
 * Offline Queue screen and tap "Sync All Now" - the same automatic-retry
 * guarantee media/photo uploads already have via MediaUploadWorker.
 *
 * Idempotent to run repeatedly: syncOfflineQueue() only ever acts on
 * whatever is currently queued and removes each action once it succeeds, so
 * running this worker again with an empty (or partially-drained) queue is a
 * safe no-op.
 */
class OfflineSyncWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        return try {
            val tokenManager = TokenManager(applicationContext)
            val offlineQueueManager = OfflineQueueManager(applicationContext)
            val repository = VisitRepository(
                visitApi = ApiClient.createVisitApi(tokenManager),
                customerApi = ApiClient.createCustomerApi(tokenManager),
                geoApi = ApiClient.createGeoApi(tokenManager),
                offlineQueueManager = offlineQueueManager,
            )
            // A conflict is a legitimate, already-recorded outcome (surfaced
            // to the user on the Offline Queue screen), not a worker failure
            // - retrying it wouldn't change anything. Only a genuine
            // exception below is worth WorkManager's own retry/backoff.
            repository.syncOfflineQueue()
            Result.success()
        } catch (e: Exception) {
            Result.retry()
        }
    }
}
