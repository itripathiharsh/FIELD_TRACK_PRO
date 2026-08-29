package com.fieldtrackpro.android.data.local

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import java.util.UUID

data class PendingAction(
    val id: String = UUID.randomUUID().toString(),
    val userId: String? = null,
    val visitId: String,
    val actionType: String, // "CHECK_IN" or "CHECK_OUT"
    val latitude: Double,
    val longitude: Double,
    val timestamp: Long = System.currentTimeMillis(),
    val notes: String? = null,
    val accuracyM: Double? = null,
    val isMockLocation: Boolean = false
)

/**
 * Offline queue manager for check-in and check-out actions.
 *
 * APP-ATT-005: EncryptedSharedPreferences storage with Android Keystore-backed AES-256-GCM.
 * Seamless one-time data migration from legacy plaintext preferences.
 * User-scoped offline queue to prevent User A actions from executing under User B session.
 */
class OfflineQueueManager(context: Context) {

    private val prefs: SharedPreferences = createPreferences(context)
    private val gson = Gson()
    private val lock = Any()

    companion object {
        private const val TAG = "OfflineQueueManager"
        private const val SECURE_PREFS_NAME = "fieldtrackpro_offline_queue_secure"
        private const val LEGACY_PREFS_NAME = "fieldtrackpro_offline_queue"

        private const val KEY_PENDING_QUEUE = "pending_queue"
        private const val KEY_CONFLICTS = "sync_conflicts"

        private fun createPreferences(context: Context): SharedPreferences {
            val masterKey = MasterKey.Builder(context)
                .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                .build()

            val secure = EncryptedSharedPreferences.create(
                context,
                SECURE_PREFS_NAME,
                masterKey,
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
            )

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
                editor.apply()
                legacy.edit().clear().apply()
            }

            return secure
        }
    }

    fun enqueueAction(action: PendingAction) = synchronized(lock) {
        val currentQueue = getQueue().toMutableList()
        val existingIndex = currentQueue.indexOfFirst {
            it.visitId == action.visitId && it.actionType == action.actionType
        }
        if (existingIndex >= 0) {
            currentQueue[existingIndex] = action
        } else {
            currentQueue.add(action)
        }
        saveQueue(currentQueue)
    }

    fun getQueue(): List<PendingAction> = synchronized(lock) {
        val json = prefs.getString(KEY_PENDING_QUEUE, "[]") ?: "[]"
        val type = object : TypeToken<List<PendingAction>>() {}.type
        return try {
            gson.fromJson(json, type) ?: emptyList()
        } catch (e: Exception) {
            emptyList()
        }
    }

    fun getQueueForUser(userId: String?): List<PendingAction> = synchronized(lock) {
        val all = getQueue()
        if (userId == null) return all
        return all.filter { it.userId == null || it.userId == userId }
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

    private fun saveQueue(queue: List<PendingAction>) {
        val json = gson.toJson(queue)
        prefs.edit().putString(KEY_PENDING_QUEUE, json).apply()
    }

    fun addConflict(conflict: SyncConflict) = synchronized(lock) {
        val conflicts = getConflicts().toMutableList()
        conflicts.add(conflict)
        val json = gson.toJson(conflicts)
        prefs.edit().putString(KEY_CONFLICTS, json).apply()
    }

    fun saveConflict(conflict: SyncConflict) = addConflict(conflict)

    fun removeConflict(conflictId: String) = synchronized(lock) {
        val currentConflicts = getConflicts().toMutableList()
        currentConflicts.removeAll { it.id == conflictId }
        val json = gson.toJson(currentConflicts)
        prefs.edit().putString(KEY_CONFLICTS, json).apply()
    }

    fun getConflicts(): List<SyncConflict> = synchronized(lock) {
        val json = prefs.getString(KEY_CONFLICTS, "[]") ?: "[]"
        val type = object : TypeToken<List<SyncConflict>>() {}.type
        return try {
            gson.fromJson(json, type) ?: emptyList()
        } catch (e: Exception) {
            emptyList()
        }
    }

    fun clearConflicts() = synchronized(lock) {
        prefs.edit().remove(KEY_CONFLICTS).apply()
    }
}
