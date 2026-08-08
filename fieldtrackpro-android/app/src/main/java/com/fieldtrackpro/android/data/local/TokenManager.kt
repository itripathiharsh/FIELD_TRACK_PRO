package com.fieldtrackpro.android.data.local

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/**
 * Credential storage.
 *
 * FT-027: tokens were kept in plaintext SharedPreferences. Security Design
 * section 1 requires "Android Keystore-backed encrypted storage (never
 * SharedPreferences in plaintext)". On a rooted or backed-up device the
 * previous file exposed a working access token and a 7-day refresh token.
 *
 * Storage is now EncryptedSharedPreferences with an AES-256-GCM master key held
 * in the Android Keystore, so the key material never leaves hardware-backed
 * storage and the file is unreadable outside the app.
 *
 * Requires `androidx.security:security-crypto` (declared in app/build.gradle.kts).
 */
class TokenManager(context: Context) {

    private val prefs: SharedPreferences = createPreferences(context)

    companion object {
        private const val TAG = "TokenManager"
        private const val PREFS_NAME = "fieldtrackpro_secure_prefs"
        private const val LEGACY_PREFS_NAME = "fieldtrackpro_prefs"

        private const val KEY_ACCESS_TOKEN = "access_token"
        private const val KEY_REFRESH_TOKEN = "refresh_token"
        private const val KEY_USER_NAME = "user_name"
        private const val KEY_USER_EMAIL = "user_email"
        private const val KEY_USER_ROLE = "user_role"

        private fun createPreferences(context: Context): SharedPreferences {
            val masterKey = MasterKey.Builder(context)
                .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                .build()

            val secure = EncryptedSharedPreferences.create(
                context,
                PREFS_NAME,
                masterKey,
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
            )

            // One-time migration: destroy any plaintext credentials written by
            // the previous build. Tokens are deliberately NOT copied across -
            // they must be assumed compromised, so the user signs in again.
            val legacy = context.getSharedPreferences(LEGACY_PREFS_NAME, Context.MODE_PRIVATE)
            if (legacy.contains(KEY_ACCESS_TOKEN) || legacy.contains(KEY_REFRESH_TOKEN)) {
                Log.i(TAG, "Clearing legacy plaintext credential store (FT-027)")
                legacy.edit().clear().apply()
            }

            return secure
        }
    }

    fun saveTokens(accessToken: String, refreshToken: String) {
        prefs.edit()
            .putString(KEY_ACCESS_TOKEN, accessToken)
            .putString(KEY_REFRESH_TOKEN, refreshToken)
            .apply()
    }

    fun getAccessToken(): String? = prefs.getString(KEY_ACCESS_TOKEN, null)?.ifBlank { null }

    fun getRefreshToken(): String? = prefs.getString(KEY_REFRESH_TOKEN, null)?.ifBlank { null }

    fun saveUserProfile(name: String, email: String?, role: String) {
        prefs.edit()
            .putString(KEY_USER_NAME, name)
            .putString(KEY_USER_EMAIL, email ?: "")
            .putString(KEY_USER_ROLE, role)
            .apply()
    }

    fun getUserName(): String? = prefs.getString(KEY_USER_NAME, null)?.ifBlank { null }

    fun getUserEmail(): String? = prefs.getString(KEY_USER_EMAIL, null)?.ifBlank { null }

    /**
     * The signed-in user's role, or null when unknown.
     *
     * Deliberately NOT defaulted to "EMPLOYEE": inventing a role client-side is
     * the same class of defect as FT-001 on the web. The server decides, and an
     * absent value means "not signed in".
     */
    fun getUserRole(): String? = prefs.getString(KEY_USER_ROLE, null)?.ifBlank { null }

    fun clear() {
        prefs.edit().clear().apply()
    }

    fun isLoggedIn(): Boolean = getAccessToken() != null
}
