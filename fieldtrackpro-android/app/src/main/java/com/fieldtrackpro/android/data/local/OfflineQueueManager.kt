package com.fieldtrackpro.android.data.local

import android.content.Context
import android.content.SharedPreferences
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import java.util.UUID

data class PendingAction(
    val id: String = UUID.randomUUID().toString(),
    val visitId: String,
    val actionType: String, // "CHECK_IN" or "CHECK_OUT"
    val latitude: Double,
    val longitude: Double,
    val timestamp: Long = System.currentTimeMillis(),
    val notes: String? = null
)

class OfflineQueueManager(context: Context) {
    private val prefs: SharedPreferences =
        context.getSharedPreferences("fieldtrackpro_offline_queue", Context.MODE_PRIVATE)
    private val gson = Gson()

    companion object {
        private const val KEY_PENDING_QUEUE = "pending_queue"
    }

    fun enqueueAction(action: PendingAction) {
        val currentQueue = getQueue().toMutableList()
        currentQueue.add(action)
        saveQueue(currentQueue)
    }

    fun getQueue(): List<PendingAction> {
        val json = prefs.getString(KEY_PENDING_QUEUE, "[]") ?: "[]"
        val type = object : TypeToken<List<PendingAction>>() {}.type
        return try {
            gson.fromJson(json, type) ?: emptyList()
        } catch (e: Exception) {
            emptyList()
        }
    }

    fun removeAction(actionId: String) {
        val currentQueue = getQueue().toMutableList()
        currentQueue.removeAll { it.id == actionId }
        saveQueue(currentQueue)
    }

    fun clearQueue() {
        prefs.edit().remove(KEY_PENDING_QUEUE).apply()
    }

    private fun saveQueue(queue: List<PendingAction>) {
        val json = gson.toJson(queue)
        prefs.edit().putString(KEY_PENDING_QUEUE, json).apply()
    }
}
