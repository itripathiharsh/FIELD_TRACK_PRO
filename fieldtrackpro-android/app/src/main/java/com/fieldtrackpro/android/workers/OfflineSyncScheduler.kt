package com.fieldtrackpro.android.workers

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkRequest
import java.util.concurrent.TimeUnit

/**
 * Enqueues [OfflineSyncWorker] so a queued check-in/check-out (see
 * OfflineQueueManager) is retried automatically the next time the device has
 * connectivity, rather than only when the rep manually opens the Offline
 * Queue screen and taps "Sync All Now". Mirrors the same
 * network-constraint-plus-backoff idiom already used by
 * UploadRetryScheduler for media/photo retries.
 *
 * A single, uniquely-named work request is used (REPLACE policy) since one
 * run of the worker drains the entire queue - there is never a reason to
 * have more than one sync attempt pending at a time.
 */
object OfflineSyncScheduler {

    private const val UNIQUE_WORK_NAME = "offline_visit_sync"

    private val SYNC_CONSTRAINTS = Constraints.Builder()
        .setRequiredNetworkType(NetworkType.CONNECTED)
        .build()

    /** Call this whenever an action is added to the offline queue. */
    fun scheduleSync(context: Context) {
        val request = OneTimeWorkRequestBuilder<OfflineSyncWorker>()
            .setConstraints(SYNC_CONSTRAINTS)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, WorkRequest.MIN_BACKOFF_MILLIS, TimeUnit.MILLISECONDS)
            .build()
        WorkManager.getInstance(context)
            .enqueueUniqueWork(UNIQUE_WORK_NAME, ExistingWorkPolicy.REPLACE, request)
    }
}
