package com.fieldtrackpro.android.data.local

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.security.KeyStore

/**
 * Shared, crash-safe factory for Keystore-backed [EncryptedSharedPreferences].
 *
 * The Android Keystore master key can become unusable (restored device backup, OS upgrade, key
 * invalidated by a lock-screen change, corrupted file). The AndroidX security-crypto classes then
 * throw GeneralSecurityException / AEADBadTagException on every launch, which previously caused a
 * crash loop. Here we delete the unreadable prefs file and the keystore alias and recreate them,
 * so the user simply ends up logged out. If recreation also fails, null is returned and the
 * caller must degrade gracefully.
 */
internal object SecurePrefs {
    private const val TAG = "SecurePrefs"

    fun create(context: Context, fileName: String): SharedPreferences? {
        return try {
            open(context, fileName)
        } catch (e: Exception) {
            // GeneralSecurityException, AEADBadTagException, IOException, KeyStoreException, ...
            Log.e(TAG, "Secure storage '$fileName' unreadable (${e.javaClass.simpleName}); resetting")
            reset(context, fileName)
            try {
                open(context, fileName)
            } catch (e2: Exception) {
                Log.e(TAG, "Secure storage '$fileName' could not be recreated (${e2.javaClass.simpleName})")
                null
            }
        }
    }

    private fun open(context: Context, fileName: String): SharedPreferences {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        return EncryptedSharedPreferences.create(
            context,
            fileName,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    }

    private fun reset(context: Context, fileName: String) {
        try {
            context.deleteSharedPreferences(fileName)
        } catch (e: Exception) {
            Log.w(TAG, "Could not delete prefs file '$fileName'")
        }
        try {
            val keyStore = KeyStore.getInstance("AndroidKeyStore")
            keyStore.load(null)
            keyStore.deleteEntry(MasterKey.DEFAULT_MASTER_KEY_ALIAS)
        } catch (e: Exception) {
            Log.w(TAG, "Could not delete keystore alias")
        }
    }
}

/** Minimal in-memory [SharedPreferences] used as a degraded fallback and in unit tests. */
class InMemorySharedPreferences : SharedPreferences {
    private val map = HashMap<String, Any?>()

    @Synchronized override fun getAll(): MutableMap<String, *> = HashMap(map)
    @Synchronized override fun getString(key: String?, defValue: String?): String? = map[key] as? String ?: defValue
    @Suppress("UNCHECKED_CAST")
    @Synchronized override fun getStringSet(key: String?, defValues: MutableSet<String>?): MutableSet<String>? =
        map[key] as? MutableSet<String> ?: defValues
    @Synchronized override fun getInt(key: String?, defValue: Int): Int = map[key] as? Int ?: defValue
    @Synchronized override fun getLong(key: String?, defValue: Long): Long = map[key] as? Long ?: defValue
    @Synchronized override fun getFloat(key: String?, defValue: Float): Float = map[key] as? Float ?: defValue
    @Synchronized override fun getBoolean(key: String?, defValue: Boolean): Boolean = map[key] as? Boolean ?: defValue
    @Synchronized override fun contains(key: String?): Boolean = map.containsKey(key)
    override fun registerOnSharedPreferenceChangeListener(l: SharedPreferences.OnSharedPreferenceChangeListener?) {}
    override fun unregisterOnSharedPreferenceChangeListener(l: SharedPreferences.OnSharedPreferenceChangeListener?) {}

    override fun edit(): SharedPreferences.Editor = object : SharedPreferences.Editor {
        private val pending = HashMap<String, Any?>()
        private val removals = HashSet<String>()
        private var clearAll = false

        override fun putString(key: String?, value: String?) = apply { pending[key!!] = value }
        override fun putStringSet(key: String?, values: MutableSet<String>?) = apply { pending[key!!] = values }
        override fun putInt(key: String?, value: Int) = apply { pending[key!!] = value }
        override fun putLong(key: String?, value: Long) = apply { pending[key!!] = value }
        override fun putFloat(key: String?, value: Float) = apply { pending[key!!] = value }
        override fun putBoolean(key: String?, value: Boolean) = apply { pending[key!!] = value }
        override fun remove(key: String?) = apply { removals.add(key!!) }
        override fun clear() = apply { clearAll = true }
        override fun commit(): Boolean {
            apply()
            return true
        }
        override fun apply() {
            synchronized(this@InMemorySharedPreferences) {
                if (clearAll) map.clear()
                removals.forEach { map.remove(it) }
                pending.forEach { (k, v) -> if (v == null) map.remove(k) else map[k] = v }
            }
        }
    }
}
