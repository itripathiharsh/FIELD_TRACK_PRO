package com.fieldtrackpro.android.workers

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.PaymentProofStore
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.SyncResult
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.VisitRepository
import java.io.IOException

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

    /** Outcome the worker should report to WorkManager. */
    enum class Outcome { SUCCESS, RETRY, FAILURE }

    companion object {
        /** Non-network errors give up after this many attempts instead of retrying forever. */
        const val MAX_NON_NETWORK_ATTEMPTS = 8

        /** Maximum attempts for "401 although tokens are still stored" before giving up (backoff is exponential). */
        const val MAX_AUTH_RETRIES = 6

        /**
         * Maps a sync run to a WorkManager outcome.
         *
         * @param sessionStillValid true while TokenManager still holds a session (tokens not cleared). A 401 with the
         *  session intact is TRANSIENT (e.g. refresh blocked by a Render cold start / flaky network): WorkManager
         *  never re-runs a one-time request that returned failure(), so report retry() with backoff instead. Only a
         *  session that is truly gone (tokens cleared) is a failure; a fresh login re-schedules the sync.
         */
        fun outcomeFor(result: SyncResult, sessionStillValid: Boolean = false, runAttemptCount: Int = 0): Outcome = when {
            // Forced password change: sync is paused (not failed). It is re-scheduled once the password is changed.
            result.pausedForPasswordChange -> Outcome.SUCCESS
            result.pausedForAuth && sessionStillValid && runAttemptCount < MAX_AUTH_RETRIES -> Outcome.RETRY
            // Session gone: the queue is intact but NOT synced. Do not report success.
            result.pausedForAuth -> Outcome.FAILURE
            // Network/5xx failures keep retrying with exponential backoff.
            result.retryableFailures > 0 -> Outcome.RETRY
            else -> Outcome.SUCCESS
        }

        /** Maps an exception to an outcome: network errors always retry, others are capped. */
        fun outcomeForException(e: Exception, runAttemptCount: Int): Outcome = when {
            e is IOException -> Outcome.RETRY
            runAttemptCount >= MAX_NON_NETWORK_ATTEMPTS -> Outcome.FAILURE
            else -> Outcome.RETRY
        }
    }

    override suspend fun doWork(): Result {
        return try {
            val tokenManager = TokenManager.getInstance(applicationContext)
            val activeUserId = tokenManager.getUserId()
            if (!tokenManager.isLoggedIn() || activeUserId.isNullOrBlank()) {
                // No active user session - nothing to sync safely
                return Result.success()
            }
            if (tokenManager.isPasswordChangeRequired()) {
                // Forced password change pending: every authenticated call would 403. Pause (not fail, not
                // conflict); the change-password success path re-schedules the sync.
                return Result.success()
            }

            val offlineQueueManager = OfflineQueueManager.getInstance(applicationContext)

            // Housekeeping: a payment proof photo captured but never submitted (app killed
            // between the file copy and the queue entry being written) leaks a file nothing
            // references. Bound how long that survives rather than leaving it forever.
            val referencedProofPaths = (
                offlineQueueManager.getQueue().mapNotNull { it.paymentPayload?.proofPaths } +
                    // Proofs kept after a too-large rejection live on in conflicts until retake/discard.
                    offlineQueueManager.getConflicts().mapNotNull { it.pendingAction.paymentPayload?.proofPaths }
                ).flatten().toSet()
            PaymentProofStore.pruneOrphaned(applicationContext, referencedProofPaths)

            val repository = VisitRepository(
                visitApi = ApiClient.createVisitApi(tokenManager),
                customerApi = ApiClient.createCustomerApi(tokenManager),
                geoApi = ApiClient.createGeoApi(tokenManager),
                offlineQueueManager = offlineQueueManager,
                tokenManager = tokenManager
            )
            // A conflict is a legitimate, already-recorded outcome (surfaced
            // to the user on the Offline Queue screen), not a worker failure
            // - retrying it wouldn't change anything.
            val result = repository.syncOfflineQueue(activeUserId = activeUserId)
            when (outcomeFor(result, sessionStillValid = tokenManager.isLoggedIn(), runAttemptCount = runAttemptCount)) {
                Outcome.SUCCESS -> Result.success()
                Outcome.RETRY -> Result.retry()
                Outcome.FAILURE -> Result.failure()
            }
        } catch (e: Exception) {
            when (outcomeForException(e, runAttemptCount)) {
                Outcome.RETRY -> Result.retry()
                else -> Result.failure()
            }
        }
    }
}
