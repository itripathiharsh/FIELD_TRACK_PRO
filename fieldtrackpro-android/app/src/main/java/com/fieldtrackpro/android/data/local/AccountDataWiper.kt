package com.fieldtrackpro.android.data.local

import android.content.Context
import android.util.Log
import androidx.work.WorkManager
import com.fieldtrackpro.android.notifications.NotificationTracker
import java.io.File

/**
 * Account deletion (Play policy): after the backend has accepted DELETE /api/v1/auth/me, ALL data this device
 * holds for that user is wiped, so the "unsynced items will be permanently lost" warning is true:
 *  - offline queue entries and conflicts of that user (other users' entries are untouched), quarantine backups;
 *  - payment-proof and outlet-proof private photo files those entries referenced, capture drafts, and every
 *    orphaned proof/pending-upload file;
 *  - cached prefs (notification de-dup tracker) and ALL scheduled background work (WorkManager).
 * Tokens/profile are cleared by [com.fieldtrackpro.android.data.repository.AuthRepository] (same success path).
 *
 * The file/Android side effects are injected so the data-wiping logic is unit-testable on the JVM.
 */
class AccountDataWiper(
    private val queue: OfflineQueueManager,
    private val deleteFile: (String) -> Unit = { try { File(it).delete() } catch (_: Exception) {} },
    private val clearDrafts: (userId: String) -> Unit = {},
    private val extraCleanup: () -> Unit = {}
) {
    /** Returns the number of private files deleted that were referenced by the user's queue entries/conflicts. */
    fun wipe(userId: String?): Int {
        var deleted = 0
        if (!userId.isNullOrBlank()) {
            val paths = queue.purgeUser(userId).distinct()
            paths.forEach { deleteFile(it); deleted++ }
            try { clearDrafts(userId) } catch (e: Exception) { Log.w(TAG, "Draft cleanup skipped: ${e.javaClass.simpleName}") }
        }
        try { extraCleanup() } catch (e: Exception) { Log.w(TAG, "Extra cleanup skipped: ${e.javaClass.simpleName}") }
        return deleted
    }

    companion object {
        private const val TAG = "AccountDataWiper"

        /** Production wiring: real private-file stores, drafts, notification tracker and WorkManager. */
        fun forContext(context: Context): AccountDataWiper {
            val app = context.applicationContext
            val queue = OfflineQueueManager.getInstance(app)
            return AccountDataWiper(
                queue = queue,
                clearDrafts = { userId -> OutletProofDraftStore.create(app).clearAllForUser(userId) },
                extraCleanup = {
                    // Anything no remaining queue entry (another user's) still references is removed regardless of age.
                    val remaining = queue.getQueue().flatMap { a ->
                        a.paymentPayload?.proofPaths.orEmpty() + listOfNotNull(a.outletProofPayload?.photoPath)
                    }.toSet()
                    PaymentProofStore.pruneOrphaned(app, remaining, maxAgeMs = 0L)
                    OutletProofStore.pruneOrphanedIn(File(app.filesDir, OutletProofStore.DIR), remaining, maxAgeMs = 0L)
                    app.cacheDir.listFiles { f -> f.name.startsWith("pending_upload_") }?.forEach { it.delete() }
                    app.filesDir.listFiles { f -> f.name.startsWith("pending_signature_") }?.forEach { it.delete() }
                    NotificationTracker.clear(app)
                    try {
                        val wm = WorkManager.getInstance(app)
                        wm.cancelAllWork()
                        wm.pruneWork()
                    } catch (e: Exception) {
                        Log.w(TAG, "WorkManager cancel skipped: ${e.javaClass.simpleName}")
                    }
                }
            )
        }
    }
}
