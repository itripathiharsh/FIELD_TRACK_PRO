package com.fieldtrackpro.android.utils

import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Central event bus for application-wide session lifecycle events and deep link dispatch.
 *
 * APP-AUTH-001 & APP-NAV-001: Global session expiration and logout dispatch.
 * Deep links are held pending until active session viability is confirmed by Splash / Auth.
 */
object SessionManager {
    private val _sessionExpiredEvent = MutableSharedFlow<Unit>(replay = 1, extraBufferCapacity = 1)
    val sessionExpiredEvent: SharedFlow<Unit> = _sessionExpiredEvent.asSharedFlow()

    private val _pendingDeepLinkVisitId = MutableStateFlow<String?>(null)
    val pendingDeepLinkVisitId: StateFlow<String?> = _pendingDeepLinkVisitId.asStateFlow()

    fun notifySessionExpired() {
        _sessionExpiredEvent.tryEmit(Unit)
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

    @OptIn(ExperimentalCoroutinesApi::class)
    fun reset() {
        _sessionExpiredEvent.resetReplayCache()
        _pendingDeepLinkVisitId.value = null
    }
}
