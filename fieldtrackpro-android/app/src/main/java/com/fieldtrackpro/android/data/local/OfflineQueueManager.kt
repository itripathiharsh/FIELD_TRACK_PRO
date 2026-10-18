package com.fieldtrackpro.android.data.local

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import com.fieldtrackpro.android.workers.OfflineSyncScheduler
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import com.google.gson.annotations.SerializedName
import java.util.UUID

// @SerializedName values are the exact legacy persisted JSON field names (Gson used the Kotlin property
// names). They keep the persisted queue readable across R8 obfuscation and app upgrades.
data class PendingAction(
    @SerializedName("id") val id: String = UUID.randomUUID().toString(),
    @SerializedName("userId") val userId: String? = null,
    @SerializedName("visitId") val visitId: String,
    @SerializedName("actionType") val actionType: String, // "CHECK_IN", "CHECK_OUT", "START_DAY", "END_DAY", "PAYMENT_CREATE"
    @SerializedName("latitude") val latitude: Double,
    @SerializedName("longitude") val longitude: Double,
    @SerializedName("timestamp") val timestamp: Long = System.currentTimeMillis(),
    @SerializedName("notes") val notes: String? = null,
    @SerializedName("accuracyM") val accuracyM: Double? = null,
    @SerializedName("isMockLocation") val isMockLocation: Boolean = false,
    // Only set for actionType == PAYMENT_CREATE. Nullable so pre-existing persisted entries still deserialize.
    @SerializedName("paymentPayload") val paymentPayload: PaymentQueuePayload? = null,
    // Only set for actionType == OUTLET_PROOF (live outlet photo + GPS bundle). Nullable: older entries still deserialize.
    @SerializedName("outletProofPayload") val outletProofPayload: OutletProofPayload? = null
) {
    companion object {
        const val TYPE_PAYMENT_CREATE = "PAYMENT_CREATE"
        const val TYPE_OUTLET_PROOF = "OUTLET_PROOF"
        /** Placeholder action carried by the notice raised when a corrupted queue blob had to be quarantined. */
        const val TYPE_QUEUE_RECOVERY = "QUEUE_RECOVERY"
    }

    val isPayment: Boolean get() = actionType == TYPE_PAYMENT_CREATE

    val isOutletProof: Boolean get() = actionType == TYPE_OUTLET_PROOF
}

/**
 * Offline queue manager for check-in and check-out actions.
 *
 * APP-ATT-005: EncryptedSharedPreferences storage with Android Keystore-backed AES-256-GCM.
 * Seamless one-time data migration from legacy plaintext preferences.
 * User-scoped offline queue to prevent User A actions from executing under User B session.
 */
class OfflineQueueManager internal constructor(
    private val prefs: SharedPreferences,
    /** Last user id signed in before the current session (TokenManager); attributes legacy unowned entries. */
    private val previousUserIdProvider: () -> String? = { null },
    private val onActionEnqueued: () -> Unit = {}
) {

    /**
     * Every enqueue (VisitRepository, WorkdayRepository, any future site) schedules a connectivity-constrained
     * [OfflineSyncScheduler] run with exponential backoff, so queued actions sync automatically.
     */
    constructor(context: Context) : this(
        createPreferences(context),
        previousUserIdProvider = { TokenManager.getInstance(context.applicationContext).getLastUserId() },
        onActionEnqueued = syncScheduler(context)
    )

    private val gson = Gson()

    companion object {
        private const val TAG = "OfflineQueueManager"
        // Process-wide, NOT per-instance: MainActivity, WorkdayViewModel, OfflineSyncWorker and
        // FieldTrackApp each construct their own OfflineQueueManager(context), all backed by the
        // SAME underlying SharedPreferences file (Context.getSharedPreferences caches by name).
        // A per-instance lock would only serialise a read-modify-write of the queue against
        // OTHER calls through that same instance, not against a different instance's concurrent
        // read-modify-write of the same file - e.g. the UI thread enqueuing a new payment and
        // OfflineSyncWorker removing a synced item could race and one write clobber the other,
        // since saveQueue() persists the whole list as one blob. One shared lock across every
        // instance actually serialises them.
        private val lock = Any()
        private val instanceLock = Any()
        @Volatile private var sharedInstance: OfflineQueueManager? = null

        /**
         * Application-wide shared instance (one Keystore/EncryptedSharedPreferences open for the whole process).
         * Prefer this over OfflineQueueManager(context); every read-modify-write is additionally serialised by the
         * process-wide [lock], so even directly constructed instances cannot lose each other's updates.
         */
        fun getInstance(context: Context): OfflineQueueManager =
            sharedInstance ?: synchronized(instanceLock) {
                sharedInstance ?: OfflineQueueManager(context.applicationContext).also { manager ->
                    // One-time upgrade (flag-guarded): legacy un-owned entries belong to the user still signed in at
                    // update time. Done HERE, before the shared instance is published, so no reader can ever see the
                    // queue before this attribution happened (even though app start-up now warms it off the main thread).
                    try {
                        manager.migrateLegacyForActiveSession(
                            TokenManager.getInstance(context.applicationContext).getActiveSessionUserId()
                        )
                    } catch (e: Exception) {
                        Log.w(TAG, "Legacy queue migration skipped: ${e.javaClass.simpleName}")
                    }
                    sharedInstance = manager
                }
            }

        private const val QUARANTINE_SUFFIX = "_corrupt_"
        private val queueType = object : TypeToken<List<PendingAction?>>() {}.type
        private val conflictsType = object : TypeToken<List<SyncConflict?>>() {}.type
        private const val SECURE_PREFS_NAME = "fieldtrackpro_offline_queue_secure"
        private const val LEGACY_PREFS_NAME = "fieldtrackpro_offline_queue"

        private const val KEY_PENDING_QUEUE = "pending_queue"
        private const val KEY_CONFLICTS = "sync_conflicts"
        private const val KEY_ACTIVE_SESSION_MIGRATION_DONE = "legacy_active_session_migration_done"

        private fun syncScheduler(context: Context): () -> Unit {
            val appContext = context.applicationContext
            return { OfflineSyncScheduler.scheduleSync(appContext) }
        }

        private fun createPreferences(context: Context): SharedPreferences {
            // SecurePrefs recovers from an unreadable keystore/prefs file by resetting it (queue is lost
            // rather than crash-looping). If even that fails, fall back to a non-persistent store.
            val secure = SecurePrefs.create(context, SECURE_PREFS_NAME) ?: InMemorySharedPreferences()

            // Safe migration: transfer any pending queue or conflict items from plaintext to secure store
            val legacy = context.getSharedPreferences(LEGACY_PREFS_NAME, Context.MODE_PRIVATE)
            val legacyQueue = legacy.getString(KEY_PENDING_QUEUE, null)
            val legacyConflicts = legacy.getString(KEY_CONFLICTS, null)

            if (!legacyQueue.isNullOrBlank() || !legacyConflicts.isNullOrBlank()) {
                Log.i(TAG, "Migrating pending offline actions to secure encrypted store (APP-ATT-005)")
                val editor = secure.edit()
                if (!legacyQueue.isNullOrBlank() && !secure.contains(KEY_PENDING_QUEUE)) {
                    editor.putString(KEY_PENDING_QUEUE, legacyQueue)
                }
                if (!legacyConflicts.isNullOrBlank() && !secure.contains(KEY_CONFLICTS)) {
                    editor.putString(KEY_CONFLICTS, legacyConflicts)
                }
                editor.commit()
                legacy.edit().clear().apply()
            }

            return secure
        }
    }

    fun enqueueAction(action: PendingAction) {
        synchronized(lock) {
            val currentQueue = getQueue().toMutableList()
            // Per-user: User B's action must never replace (or be replaced by) User A's queued action.
            val existingIndex = currentQueue.indexOfFirst {
                if (action.isOutletProof) {
                    // Dedup only on the stable idempotency key (same capture, same user).
                    val key = action.outletProofPayload?.idempotencyKey
                    it.isOutletProof && it.userId == action.userId && key != null &&
                        it.outletProofPayload?.idempotencyKey == key
                } else if (action.isPayment) {
                    // A visit can have several payments: dedup only on the stable idempotency key.
                    val key = action.paymentPayload?.idempotencyKey
                    it.isPayment && it.userId == action.userId && key != null &&
                        it.paymentPayload?.idempotencyKey == key
                } else {
                    it.visitId == action.visitId && it.actionType == action.actionType && it.userId == action.userId
                }
            }
            if (existingIndex >= 0) {
                currentQueue[existingIndex] = action
            } else {
                currentQueue.add(action)
            }
            saveQueue(currentQueue)
        }
        try {
            onActionEnqueued()
        } catch (e: Exception) {
            Log.w(TAG, "Could not schedule offline sync: ${e.javaClass.simpleName}")
        }
    }

    /**
     * The persisted queue. A blob that cannot be parsed is NEVER silently treated as "empty": the raw JSON is first
     * copied to a quarantine key (pending_queue_corrupt_<epoch>), the live key is reset to an empty list so new
     * entries append safely instead of overwriting the evidence, and a [ConflictType.QUEUE_CORRUPTED] notice is
     * recorded so the user/support is told (see [getCorruptionBackupKeys]).
     */
    fun getQueue(): List<PendingAction> = synchronized(lock) {
        val json = prefs.getString(KEY_PENDING_QUEUE, null)
        if (json.isNullOrBlank()) return emptyList()
        return try {
            (gson.fromJson<List<PendingAction?>>(json, queueType) ?: emptyList()).filterNotNull()
        } catch (e: Exception) {
            quarantineCorruptBlob(KEY_PENDING_QUEUE, json, "offline queue")
            emptyList()
        }
    }

    /** Keys under which raw unparseable queue/conflict blobs were preserved (empty when nothing was quarantined). */
    fun getCorruptionBackupKeys(): List<String> = synchronized(lock) {
        prefs.all.keys.filter { it.contains(QUARANTINE_SUFFIX) }.sorted()
    }

    private fun quarantineCorruptBlob(key: String, raw: String, label: String) {
        var backupKey = "$key$QUARANTINE_SUFFIX${System.currentTimeMillis()}"
        while (prefs.contains(backupKey)) backupKey += "x"
        Log.e(TAG, "Unreadable $label blob quarantined under $backupKey (${raw.length} chars)")
        val notice = SyncConflict(
            pendingAction = PendingAction(
                visitId = "",
                actionType = PendingAction.TYPE_QUEUE_RECOVERY,
                latitude = 0.0,
                longitude = 0.0
            ),
            conflictType = ConflictType.QUEUE_CORRUPTED,
            serverStatus = backupKey,
            message = "Some saved offline items could not be read and were set aside (backup key $backupKey). " +
                "New items are saved normally. Please report this to support."
        )
        val editor = prefs.edit().putString(backupKey, raw).putString(key, "[]")
        // The notice goes into the conflicts list (a corrupted conflicts blob is replaced by the notice itself).
        val existingConflicts = if (key == KEY_CONFLICTS) emptyList() else readConflictsRaw()
        editor.putString(KEY_CONFLICTS, gson.toJson(existingConflicts + notice))
        editor.commit()
    }

    private fun readConflictsRaw(): List<SyncConflict> {
        val json = prefs.getString(KEY_CONFLICTS, null)
        if (json.isNullOrBlank()) return emptyList()
        return try {
            (gson.fromJson<List<SyncConflict?>>(json, conflictsType) ?: emptyList()).filterNotNull()
        } catch (e: Exception) {
            quarantineCorruptBlob(KEY_CONFLICTS, json, "conflict list")
            readConflictsRaw()
        }
    }

    /**
     * Returns ONLY the given user's queued actions. Legacy entries written before the queue was user-scoped
     * (userId == null) are adopted only when they can be attributed to this user (see [adoptUnownedEntries]);
     * otherwise they are quarantined and never synced. A null/blank user sees nothing.
     */
    fun getQueueForUser(userId: String?): List<PendingAction> = synchronized(lock) {
        if (userId.isNullOrBlank()) return emptyList()
        adoptUnownedEntries(userId, previousUserIdProvider())
        return getQueue().filter { it.userId == userId }
    }

    /** Conflicts (failed/unavailable actions) belonging to the given user only. Quarantined items are excluded. */
    fun getConflictsForUser(userId: String?): List<SyncConflict> = synchronized(lock) {
        if (userId.isNullOrBlank()) return emptyList()
        adoptUnownedEntries(userId, previousUserIdProvider())
        return getConflicts().filter { it.pendingAction.userId == userId }
    }

    /**
     * Quarantined legacy items (no owner). The UI must only show these after an explicit user confirmation.
     * They are never synced.
     */
    fun getQuarantinedConflicts(): List<SyncConflict> = synchronized(lock) {
        getConflicts().filter { it.pendingAction.userId == null }
    }

    /**
     * Idempotent migration of entries persisted by older builds that have no userId.
     *  - If [previousUserId] (last stored signed-in user) equals [userId], the entries are attributed to [userId].
     *  - Otherwise ownership cannot be proven: queue entries are moved out of the queue into a quarantined
     *    [ConflictType.UNOWNED_LEGACY] conflict (userId stays null, so no employee syncs or sees them
     *    automatically).
     */
    fun adoptUnownedEntries(userId: String, previousUserId: String?): Unit = synchronized(lock) {
        if (userId.isBlank()) return
        val attributable = !previousUserId.isNullOrBlank() && previousUserId == userId
        val queue = getQueue()
        if (queue.any { it.userId == null }) {
            if (attributable) {
                saveQueue(queue.map { if (it.userId == null) it.copy(userId = userId) else it })
            } else {
                val conflicts = getConflicts().toMutableList()
                queue.filter { it.userId == null }.forEach { legacy ->
                    conflicts.removeAll { it.pendingAction.id == legacy.id }
                    conflicts.add(
                        SyncConflict(
                            pendingAction = legacy,
                            conflictType = ConflictType.UNOWNED_LEGACY,
                            serverStatus = null,
                            message = SyncErrorPolicy.UNOWNED_LEGACY_MESSAGE
                        )
                    )
                }
                saveQueue(queue.filter { it.userId != null })
                saveConflicts(conflicts)
            }
        }
        val conflicts = getConflicts()
        // Already-quarantined items (UNOWNED_LEGACY) are never re-adopted: ownership was judged once.
        fun adoptable(c: SyncConflict) = c.pendingAction.userId == null && c.conflictType != ConflictType.UNOWNED_LEGACY
        if (attributable && conflicts.any { adoptable(it) }) {
            saveConflicts(conflicts.map {
                if (adoptable(it)) it.copy(pendingAction = it.pendingAction.copy(userId = userId)) else it
            })
        }
    }

    /**
     * One-time (per install) upgrade path. Before user-scoped queues the queue was single and synced by whoever
     * was signed in, so the user of the ACTIVE session at upgrade time is the only attributable owner of
     * unowned legacy entries: they are stamped with [activeUserId] and a sync is scheduled. With no active
     * session nothing is adopted here (entries stay unowned and follow the normal last-user/quarantine rule).
     * The flag makes this run once; entries are stamped, so they are never re-adopted by anyone else.
     * Returns the number of entries adopted.
     */
    fun migrateLegacyForActiveSession(activeUserId: String?): Int {
        var adopted = 0
        synchronized(lock) {
            if (prefs.getBoolean(KEY_ACTIVE_SESSION_MIGRATION_DONE, false)) return 0
            if (!activeUserId.isNullOrBlank()) {
                adopted = getQueue().count { it.userId == null } +
                    getConflicts().count { it.pendingAction.userId == null && it.conflictType != ConflictType.UNOWNED_LEGACY }
                adoptUnownedEntries(activeUserId, activeUserId)
            }
            prefs.edit().putBoolean(KEY_ACTIVE_SESSION_MIGRATION_DONE, true).commit()
        }
        if (adopted > 0) {
            try {
                onActionEnqueued()
            } catch (e: Exception) {
                Log.w(TAG, "Could not schedule offline sync: ${e.javaClass.simpleName}")
            }
        }
        return adopted
    }

    /** Replaces a queued action in place (same id), e.g. to record sync progress. No-op if it is gone. */
    fun updateAction(action: PendingAction): Unit = synchronized(lock) {
        val queue = getQueue()
        if (queue.none { it.id == action.id }) return
        saveQueue(queue.map { if (it.id == action.id) action else it })
    }

    /**
     * Atomically takes the action out of the retry queue and records it as a conflict so the user is told
     * about it instead of it being retried forever (e.g. HTTP 404: record no longer available).
     */
    fun moveToConflict(conflict: SyncConflict): Unit = synchronized(lock) {
        val currentQueue = getQueue().toMutableList()
        currentQueue.removeAll { it.id == conflict.pendingAction.id }
        saveQueue(currentQueue)
        val conflicts = getConflicts().toMutableList()
        conflicts.removeAll { it.pendingAction.id == conflict.pendingAction.id }
        conflicts.add(conflict)
        saveConflicts(conflicts)
    }

    fun removeAction(actionId: String) = synchronized(lock) {
        val currentQueue = getQueue().toMutableList()
        currentQueue.removeAll { it.id == actionId }
        saveQueue(currentQueue)
    }

    fun clearQueue() = synchronized(lock) {
        saveQueue(emptyList())
    }

    fun clearQueueForUser(userId: String) = synchronized(lock) {
        val currentQueue = getQueue().toMutableList()
        currentQueue.removeAll { it.userId == userId }
        saveQueue(currentQueue)
    }

    private fun saveConflicts(conflicts: List<SyncConflict>) {
        // commit(), like saveQueue(): a conflict is the user's only record of an item that did not sync.
        prefs.edit().putString(KEY_CONFLICTS, gson.toJson(conflicts)).commit()
    }

    private fun saveQueue(queue: List<PendingAction>) {
        // commit(), not apply(): this blob is the entire offline queue. apply()'s async disk
        // write means a kill right after enqueuing a newly-captured payment can lose it - commit()
        // blocks until the write actually lands, closing that window. Called under `lock` already,
        // so the brief synchronous I/O only blocks other queue operations, not arbitrary callers.
        val json = gson.toJson(queue)
        prefs.edit().putString(KEY_PENDING_QUEUE, json).commit()
    }

    fun addConflict(conflict: SyncConflict) = synchronized(lock) {
        val conflicts = getConflicts().toMutableList()
        conflicts.add(conflict)
        saveConflicts(conflicts)
    }

    fun saveConflict(conflict: SyncConflict) = addConflict(conflict)

    fun removeConflict(conflictId: String) = synchronized(lock) {
        val currentConflicts = getConflicts().toMutableList()
        currentConflicts.removeAll { it.id == conflictId }
        saveConflicts(currentConflicts)
    }

    fun getConflicts(): List<SyncConflict> = synchronized(lock) { readConflictsRaw() }

    fun clearConflicts() = synchronized(lock) {
        prefs.edit().remove(KEY_CONFLICTS).commit()
        Unit
    }

    /**
     * Account deletion: removes every queue entry and conflict that belongs to [userId] (and any
     * quarantine backups). Returns the private file paths those entries referenced so the caller can
     * delete the photos. Other users' entries are left untouched.
     */
    fun purgeUser(userId: String): List<String> = synchronized(lock) {
        val queue = getQueue()
        val conflicts = getConflicts()
        val mine = queue.filter { it.userId == userId }
        val myConflicts = conflicts.filter { it.pendingAction.userId == userId }
        saveQueue(queue.filter { it.userId != userId })
        saveConflicts(conflicts.filter { it.pendingAction.userId != userId })
        val editor = prefs.edit()
        prefs.all.keys.filter { it.contains(QUARANTINE_SUFFIX) }.forEach { editor.remove(it) }
        editor.commit()
        (mine + myConflicts.map { it.pendingAction }).flatMap { a ->
            (a.paymentPayload?.proofPaths.orEmpty()) + listOfNotNull(a.outletProofPayload?.photoPath)
        }
    }
}
