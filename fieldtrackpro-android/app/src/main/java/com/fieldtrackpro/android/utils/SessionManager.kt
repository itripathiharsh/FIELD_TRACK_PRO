package com.fieldtrackpro.android.utils

import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow

/**
 * Central event bus for application-wide session lifecycle events and deep link dispatch.
 *
 * APP-AUTH-001 & APP-NAV-001: Global session expiration and logout dispatch.
 * Deep links are held pending until active session viability is confirmed by Splash / Auth.
 */
object SessionManager {
    // One-shot events (NOT a replaying SharedFlow). A conflated Channel hands each event to exactly
    // one collector exactly once: after MainActivity consumes it, a recreated activity (rotation,
    // dark-mode toggle, font-scale change...) that starts collecting again sees NOTHING, so it can
    // no longer re-deliver an already-handled "session expired" and log the user out a second time
    // (the old replay=1 SharedFlow did exactly that unless every consumer remembered to reset()).
    // An event emitted while no one is collecting (activity mid-recreation) is retained - conflated
    // to one - and delivered to the next collector, so a genuinely pending expiry is not lost.
    // clearPendingEvents() (called on a successful login) drops a stale, never-consumed event so
    // it cannot sign a brand-new session straight out again.
    private val sessionExpiredChannel = Channel<Unit>(Channel.CONFLATED)
    val sessionExpiredEvent: Flow<Unit> = sessionExpiredChannel.receiveAsFlow()

    // Same one-shot semantics: the backend answered 403 PASSWORD_CHANGE_REQUIRED, so the UI must
    // route to the forced "Set a new password" screen exactly once.
    private val passwordChangeChannel = Channel<Unit>(Channel.CONFLATED)
    val passwordChangeRequiredEvent: Flow<Unit> = passwordChangeChannel.receiveAsFlow()

    private val _pendingDeepLinkVisitId = MutableStateFlow<String?>(null)
    val pendingDeepLinkVisitId: StateFlow<String?> = _pendingDeepLinkVisitId.asStateFlow()

    fun notifySessionExpired() {
        sessionExpiredChannel.trySend(Unit)
    }

    fun notifyPasswordChangeRequired() {
        passwordChangeChannel.trySend(Unit)
    }

    /** Drops events that were emitted but never consumed (call after a successful sign-in). */
    fun clearPendingEvents() {
        while (sessionExpiredChannel.tryReceive().isSuccess) { /* drain */ }
        while (passwordChangeChannel.tryReceive().isSuccess) { /* drain */ }
    }

    fun setPendingDeepLink(visitId: String?) {
        _pendingDeepLinkVisitId.value = visitId?.ifBlank { null }
    }

    fun getPendingDeepLink(): String? = _pendingDeepLinkVisitId.value

    fun consumePendingDeepLink(): String? {
        val link = _pendingDeepLinkVisitId.value
        _pendingDeepLinkVisitId.value = null
        return link
    }

    fun reset() {
        clearPendingEvents()
        _pendingDeepLinkVisitId.value = null
    }
}
