package com.fieldtrackpro.android.data.local

import android.content.Context
import android.content.SharedPreferences
import com.google.gson.Gson

/**
 * Persists the capture that has been taken but not yet consumed (uploaded for a new outlet / queued or sent for an
 * existing one), so a process death between the shutter and the submit does not lose it - and so the SAME
 * idempotency key is reused after a restart. One draft per (user, outlet); a new outlet uses the scope "NEW".
 * Stored in encrypted prefs (it holds coordinates); degrades to in-memory if the keystore is unusable.
 */
class OutletProofDraftStore(private val prefs: SharedPreferences) {
    private val gson = Gson()

    private fun key(userId: String, customerId: String?) = "draft_${userId}_${customerId ?: NEW_SCOPE}"

    @Synchronized
    fun save(userId: String, payload: OutletProofPayload) {
        prefs.edit().putString(key(userId, payload.customerId), gson.toJson(payload)).commit()
    }

    @Synchronized
    fun get(userId: String, customerId: String?): OutletProofPayload? {
        val json = prefs.getString(key(userId, customerId), null) ?: return null
        return try { gson.fromJson(json, OutletProofPayload::class.java) } catch (e: Exception) { null }
    }

    @Synchronized
    fun clear(userId: String, customerId: String?) {
        prefs.edit().remove(key(userId, customerId)).commit()
    }

    /** Account deletion: drops every capture draft (and thereby its idempotency key) of [userId]. */
    @Synchronized
    fun clearAllForUser(userId: String) {
        val editor = prefs.edit()
        prefs.all.keys.filter { it.startsWith("draft_${userId}_") }.forEach { editor.remove(it) }
        editor.commit()
    }

    /** Photo paths of every stored draft (they must survive the orphan sweep). */
    @Synchronized
    fun allPhotoPaths(): Set<String> = prefs.all.entries
        .filter { it.key.startsWith("draft_") }
        .mapNotNull { (it.value as? String)?.let { j -> try { gson.fromJson(j, OutletProofPayload::class.java)?.photoPath } catch (e: Exception) { null } } }
        .toSet()

    companion object {
        const val NEW_SCOPE = "NEW"
        private const val PREFS_NAME = "fieldtrackpro_outlet_proof_drafts"

        fun create(context: Context): OutletProofDraftStore =
            OutletProofDraftStore(SecurePrefs.create(context.applicationContext, PREFS_NAME) ?: InMemorySharedPreferences())
    }
}
