package com.fieldtrackpro.android.utils

import com.fieldtrackpro.android.data.local.TokenManager

/** Where the app opens, decided PURELY from locally stored state (no network, so it works offline). */
enum class StartDestination { LOGIN, DASHBOARD, CHANGE_PASSWORD }

/**
 * Cold-start routing (APP-AUTH-002).
 *
 * The app used to refresh the token on every cold start. That ran outside TokenAuthenticator's lock (so it could
 * race a worker's refresh with the same single-use refresh token, which makes the backend revoke the whole token
 * family) and logged users out / sent them to Login on any failure - including being offline with queued payments.
 *
 * Now the decision is local: a stored session (access + refresh token) AND a stored user profile means the user is
 * signed in; Splash opens the dashboard immediately, even offline. An expired access token is refreshed lazily by
 * the first authenticated call through TokenAuthenticator (single-flight lock). Only a 401/403 from the refresh
 * endpoint ends the session (SessionManager event -> Login); network errors and 5xx never do.
 */
object StartRouting {
    fun decide(tokenManager: TokenManager): StartDestination = decide(
        hasAccessToken = tokenManager.isLoggedIn(),
        hasRefreshToken = tokenManager.getRefreshToken() != null,
        hasUserProfile = tokenManager.getUserId() != null,
        passwordChangeRequired = tokenManager.isPasswordChangeRequired()
    )

    fun decide(
        hasAccessToken: Boolean,
        hasRefreshToken: Boolean,
        hasUserProfile: Boolean,
        passwordChangeRequired: Boolean
    ): StartDestination = when {
        !hasAccessToken || !hasRefreshToken || !hasUserProfile -> StartDestination.LOGIN
        passwordChangeRequired -> StartDestination.CHANGE_PASSWORD
        else -> StartDestination.DASHBOARD
    }
}
