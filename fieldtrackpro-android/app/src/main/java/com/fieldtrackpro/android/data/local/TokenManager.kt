package com.fieldtrackpro.android.data.local

import android.content.Context
import android.content.SharedPreferences
import android.util.Log

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
open class TokenManager(context: Context? = null, injectedPrefs: SharedPreferences? = null) {

    private val prefs: SharedPreferences? = injectedPrefs ?: context?.let { createPreferences(it) }

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
        // Backend contract: login / GET /auth/me expose must_change_password; true => every other
        // authenticated endpoint answers 403 PASSWORD_CHANGE_REQUIRED until the password is changed.
        private const val KEY_MUST_CHANGE_PASSWORD = "must_change_password"
        private const val KEY_LAST_USER_ID = "last_user_id"
        // Durably records the user id of every successful sign-in/session restore; survives clear().
        private const val KEY_LAST_SIGNED_IN_USER_ID = "last_signed_in_user_id"

        @Volatile
        private var sharedInstance: TokenManager? = null

        /**
         * Application-wide shared instance. Prefer this over `TokenManager(context)` so that the
         * OkHttp/Retrofit singleton, workers and UI all observe the same token state.
         */
        fun getInstance(context: Context): TokenManager =
            sharedInstance ?: synchronized(this) {
                sharedInstance ?: TokenManager(context.applicationContext).also { sharedInstance = it }
            }

        private fun createPreferences(context: Context): SharedPreferences? {
            // SecurePrefs recovers from unreadable keystore/prefs state by resetting (user is logged out).
            val secure = SecurePrefs.create(context, PREFS_NAME) ?: return null

            val legacy = context.getSharedPreferences(LEGACY_PREFS_NAME, Context.MODE_PRIVATE)
            if (legacy.contains(KEY_ACCESS_TOKEN) || legacy.contains(KEY_REFRESH_TOKEN)) {
                Log.i(TAG, "Clearing legacy plaintext credential store (FT-027)")
                legacy.edit().clear().apply()
            }

            return secure
        }
    }

    open fun saveTokens(accessToken: String, refreshToken: String) {
        // commit(), not apply(): apply() queues an async disk write and returns immediately, so a
        // process kill right after a successful refresh can lose the very tokens that refresh just
        // rotated - the next launch would still have the OLD (already-rotated-away) refresh token.
        // commit() blocks until the write lands, which is acceptable here (infrequent, not UI-hot).
        prefs?.edit()
            ?.putString(KEY_ACCESS_TOKEN, accessToken)
            ?.putString(KEY_REFRESH_TOKEN, refreshToken)
            ?.commit()
    }

    /** Persists the forced-password-change flag (commit: it gates sync and routing after a process kill). */
    open fun setPasswordChangeRequired(required: Boolean) {
        val editor = prefs?.edit() ?: return
        if (required) editor.putBoolean(KEY_MUST_CHANGE_PASSWORD, true) else editor.remove(KEY_MUST_CHANGE_PASSWORD)
        editor.commit()
    }

    /** True while the signed-in account must set a new password before anything else works. */
    open fun isPasswordChangeRequired(): Boolean = prefs?.getBoolean(KEY_MUST_CHANGE_PASSWORD, false) == true

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
        // A different user replacing the stored profile: remember who was signed in before.
        // One editor, one commit for the whole operation - previously 2-3 separate edit()/apply()
        // calls, so a kill between them could persist the new profile but lose the lastUserId/
        // lastSignedIn bookkeeping that OfflineQueueManager.adoptUnownedEntries() depends on.
        val previous = getUserId()
        val lastSignedIn = getLastSignedInUserId()
        val editor = prefs?.edit()
        if (previous != null && previous != id) {
            editor?.putString(KEY_LAST_USER_ID, previous)
        } else if (previous == null && lastSignedIn != null && lastSignedIn != id) {
            // Logged out (clear()) and a DIFFERENT user is now signing in: the earlier user is the "previous" one.
            editor?.putString(KEY_LAST_USER_ID, lastSignedIn)
        }
        if (!id.isNullOrBlank()) {
            editor?.putString(KEY_LAST_SIGNED_IN_USER_ID, id)
        }
        editor
            ?.putString(KEY_USER_ID, id ?: "")
            ?.putString(KEY_USER_NAME, name)
            ?.putString(KEY_USER_EMAIL, email ?: "")
            ?.putString(KEY_USER_ROLE, role)
            ?.putString(KEY_USER_PHONE, phone ?: "")
            ?.putString(KEY_EMPLOYEE_CODE, employeeCode ?: "")
            ?.putString(KEY_TERRITORY_NAME, territoryName ?: "")
            ?.commit()
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

    /**
     * The user id signed in before the current session (recorded on logout/user switch, kept across [clear]).
     * Used only to decide whether legacy un-owned offline-queue entries can be attributed to a user.
     */
    open fun getLastUserId(): String? = prefs?.getString(KEY_LAST_USER_ID, null)?.ifBlank { null }

    /** The most recent user id that successfully signed in (recorded at login, kept across [clear]). */
    open fun getLastSignedInUserId(): String? =
        prefs?.getString(KEY_LAST_SIGNED_IN_USER_ID, null)?.ifBlank { null }

    /** User id of the ACTIVE session (valid stored access token + stored user id), else null. */
    open fun getActiveSessionUserId(): String? = if (isLoggedIn()) getUserId() else null

    open fun clear() {
        // One editor, one commit: clear() + putString() on the SAME editor is well-defined
        // (the clear applies first, then the puts land), so this is a single atomic operation
        // instead of the previous 2-4 separate edit()/apply() calls. A kill between those used to
        // leave the session correctly cleared but permanently lose KEY_LAST_USER_ID/
        // KEY_LAST_SIGNED_IN_USER_ID, which adoptUnownedEntries() needs to attribute legacy queue
        // entries - losing it could strand queued items as "unowned".
        val fcmToken = getFcmToken()
        val lastUserId = getUserId() ?: getLastUserId()
        val lastSignedIn = getUserId() ?: getLastSignedInUserId()
        val editor = prefs?.edit()?.clear()
        if (fcmToken != null) {
            editor?.putString(KEY_FCM_TOKEN, fcmToken)
        }
        if (lastUserId != null) {
            editor?.putString(KEY_LAST_USER_ID, lastUserId)
        }
        if (lastSignedIn != null) {
            editor?.putString(KEY_LAST_SIGNED_IN_USER_ID, lastSignedIn)
        }
        editor?.commit()
    }

    open fun isLoggedIn(): Boolean = getAccessToken() != null
}
