package com.fieldtrackpro.android.workers

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
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
 * One uniquely-named one-time request plus one uniquely-named periodic safety net. Since one run of the worker
 * drains the entire queue there is never a reason for more than one pending attempt, but an IN-FLIGHT upload must
 * never be cancelled just because the Activity was recreated (rotation, dark mode) or a new item was queued:
 *  - [scheduleSync] (an action was enqueued / user just signed in): APPEND_OR_REPLACE - never cancels a running
 *    worker; the new run starts after it, so the new item is picked up.
 *  - [ensureScheduled] (every Activity start): KEEP - a no-op while anything is pending/running - plus a KEEP
 *    periodic safety net (15 min, connected) so the queue drains even if nothing else triggers it.
 *  - [syncNow] (explicit user "Sync now"): REPLACE - the only case that may restart the run.
 */
object OfflineSyncScheduler {

    private const val UNIQUE_WORK_NAME = "offline_visit_sync"
    private const val PERIODIC_WORK_NAME = "offline_visit_sync_periodic"
    private const val PERIODIC_INTERVAL_MINUTES = 15L

    /** Exposed so the policy choice is unit-tested (a regression to REPLACE would cancel in-flight uploads). */
    val ENQUEUE_POLICY = ExistingWorkPolicy.APPEND_OR_REPLACE
    val ENSURE_POLICY = ExistingWorkPolicy.KEEP
    val SYNC_NOW_POLICY = ExistingWorkPolicy.REPLACE
    val PERIODIC_POLICY = ExistingPeriodicWorkPolicy.KEEP

    private val SYNC_CONSTRAINTS = Constraints.Builder()
        .setRequiredNetworkType(NetworkType.CONNECTED)
        .build()

    private fun oneTimeRequest() = OneTimeWorkRequestBuilder<OfflineSyncWorker>()
        .setConstraints(SYNC_CONSTRAINTS)
        .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, WorkRequest.MIN_BACKOFF_MILLIS, TimeUnit.MILLISECONDS)
        .build()

    /** Call this whenever an action is added to the offline queue (does not cancel an in-flight run). */
    fun scheduleSync(context: Context) {
        WorkManager.getInstance(context).enqueueUniqueWork(UNIQUE_WORK_NAME, ENQUEUE_POLICY, oneTimeRequest())
    }

    /** Safe to call on every Activity creation: keeps whatever is pending/running and installs the periodic net. */
    fun ensureScheduled(context: Context) {
        val wm = WorkManager.getInstance(context)
        wm.enqueueUniqueWork(UNIQUE_WORK_NAME, ENSURE_POLICY, oneTimeRequest())
        val periodic = PeriodicWorkRequestBuilder<OfflineSyncWorker>(PERIODIC_INTERVAL_MINUTES, TimeUnit.MINUTES)
            .setConstraints(SYNC_CONSTRAINTS)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, WorkRequest.MIN_BACKOFF_MILLIS, TimeUnit.MILLISECONDS)
            .build()
        wm.enqueueUniquePeriodicWork(PERIODIC_WORK_NAME, PERIODIC_POLICY, periodic)
    }

    /** Explicit user-initiated "Sync now": the only caller allowed to restart a run. */
    fun syncNow(context: Context) {
        WorkManager.getInstance(context).enqueueUniqueWork(UNIQUE_WORK_NAME, SYNC_NOW_POLICY, oneTimeRequest())
    }

    /** Cancel any pending offline sync worker on logout or session reset. */
    fun cancelSync(context: Context) {
        val wm = WorkManager.getInstance(context)
        wm.cancelUniqueWork(UNIQUE_WORK_NAME)
        wm.cancelUniqueWork(PERIODIC_WORK_NAME)
    }
}
