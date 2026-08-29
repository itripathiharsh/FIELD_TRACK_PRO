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
 */
open class TokenManager(context: Context? = null) {

    private val prefs: SharedPreferences? = context?.let { createPreferences(it) }

    companion object {
        private const val TAG = "TokenManager"
        private const val PREFS_NAME = "fieldtrackpro_secure_prefs"
        private const val LEGACY_PREFS_NAME = "fieldtrackpro_prefs"

        private const val KEY_ACCESS_TOKEN = "access_token"
        private const val KEY_REFRESH_TOKEN = "refresh_token"
        private const val KEY_USER_ID = "user_id"
        private const val KEY_USER_NAME = "user_name"
        private const val KEY_USER_EMAIL = "user_email"
        private const val KEY_USER_ROLE = "user_role"
        private const val KEY_USER_PHONE = "user_phone"
        private const val KEY_EMPLOYEE_CODE = "employee_code"
        private const val KEY_TERRITORY_NAME = "territory_name"
        private const val KEY_FCM_TOKEN = "fcm_token"

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

            val legacy = context.getSharedPreferences(LEGACY_PREFS_NAME, Context.MODE_PRIVATE)
            if (legacy.contains(KEY_ACCESS_TOKEN) || legacy.contains(KEY_REFRESH_TOKEN)) {
                Log.i(TAG, "Clearing legacy plaintext credential store (FT-027)")
                legacy.edit().clear().apply()
            }

            return secure
        }
    }

    open fun saveTokens(accessToken: String, refreshToken: String) {
        prefs?.edit()
            ?.putString(KEY_ACCESS_TOKEN, accessToken)
            ?.putString(KEY_REFRESH_TOKEN, refreshToken)
            ?.apply()
    }

    open fun getAccessToken(): String? = prefs?.getString(KEY_ACCESS_TOKEN, null)?.ifBlank { null }

    open fun getRefreshToken(): String? = prefs?.getString(KEY_REFRESH_TOKEN, null)?.ifBlank { null }

    open fun saveUserProfile(
        name: String,
        email: String?,
        role: String,
        id: String? = null,
        phone: String? = null,
        employeeCode: String? = null,
        territoryName: String? = null
    ) {
        prefs?.edit()
            ?.putString(KEY_USER_ID, id ?: "")
            ?.putString(KEY_USER_NAME, name)
            ?.putString(KEY_USER_EMAIL, email ?: "")
            ?.putString(KEY_USER_ROLE, role)
            ?.putString(KEY_USER_PHONE, phone ?: "")
            ?.putString(KEY_EMPLOYEE_CODE, employeeCode ?: "")
            ?.putString(KEY_TERRITORY_NAME, territoryName ?: "")
            ?.apply()
    }

    open fun getUserId(): String? = prefs?.getString(KEY_USER_ID, null)?.ifBlank { null }

    open fun getUserName(): String? = prefs?.getString(KEY_USER_NAME, null)?.ifBlank { null }

    open fun getUserEmail(): String? = prefs?.getString(KEY_USER_EMAIL, null)?.ifBlank { null }

    open fun getUserPhone(): String? = prefs?.getString(KEY_USER_PHONE, null)?.ifBlank { null }

    open fun getEmployeeCode(): String? = prefs?.getString(KEY_EMPLOYEE_CODE, null)?.ifBlank { null }

    open fun getTerritoryName(): String? = prefs?.getString(KEY_TERRITORY_NAME, null)?.ifBlank { null }

    open fun getUserRole(): String? = prefs?.getString(KEY_USER_ROLE, null)?.ifBlank { null }

    open fun saveFcmToken(token: String) {
        prefs?.edit()?.putString(KEY_FCM_TOKEN, token)?.apply()
    }

    open fun getFcmToken(): String? = prefs?.getString(KEY_FCM_TOKEN, null)?.ifBlank { null }

    open fun clearFcmToken() {
        prefs?.edit()?.remove(KEY_FCM_TOKEN)?.apply()
    }

    open fun clear() {
        val fcmToken = getFcmToken()
        prefs?.edit()?.clear()?.apply()
        if (fcmToken != null) {
            saveFcmToken(fcmToken)
        }
    }

    open fun isLoggedIn(): Boolean = getAccessToken() != null
}
