package com.fieldtrackpro.android.utils

import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.async
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeoutOrNull
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test

/**
 * SessionManager's session-expired signal is a one-shot event. The previous replay=1 SharedFlow re-delivered the
 * last event to every new subscriber, so each Activity recreation (rotation, dark mode) logged the user out again.
 */
class SessionManagerTest {

    @Before
    fun setUp() = SessionManager.reset()

    @After
    fun tearDown() = SessionManager.reset()

    @Test
    fun emittedEvent_isDeliveredToACollector() = runBlocking {
        SessionManager.notifySessionExpired()
        val event = withTimeoutOrNull(1000) { SessionManager.sessionExpiredEvent.first() }
        assertEquals(Unit, event)
    }

    @Test
    fun activityRecreation_doesNotRedeliverAnAlreadyHandledEvent() = runBlocking {
        // Activity #1 handles the expiry...
        SessionManager.notifySessionExpired()
        assertNotNull(withTimeoutOrNull(1000) { SessionManager.sessionExpiredEvent.first() })

        // ...then is recreated (rotation / dark mode): the NEW collector must see nothing.
        val afterRecreation = withTimeoutOrNull(300) { SessionManager.sessionExpiredEvent.first() }
        assertNull("handled event must not be replayed after recreation", afterRecreation)
        // and again for a third recreation
        assertNull(withTimeoutOrNull(100) { SessionManager.sessionExpiredEvent.first() })
    }

    @Test
    fun eventEmittedWhileNoOneCollects_isStillDeliveredOnceToTheNextCollector() = runBlocking {
        // Emitted mid-recreation (no subscriber at that moment): not lost...
        SessionManager.notifySessionExpired()
        SessionManager.notifySessionExpired() // conflated: still one logout
        assertNotNull(withTimeoutOrNull(1000) { SessionManager.sessionExpiredEvent.first() })
        // ...but delivered exactly once.
        assertNull(withTimeoutOrNull(200) { SessionManager.sessionExpiredEvent.first() })
    }

    @Test
    fun runningCollector_receivesLaterEvents() = runBlocking {
        val pending = async(start = CoroutineStart.UNDISPATCHED) {
            withTimeoutOrNull(2000) { SessionManager.sessionExpiredEvent.first() }
        }
        delay(50)
        SessionManager.notifySessionExpired()
        assertNotNull(pending.await())
    }

    @Test
    fun clearPendingEvents_dropsAStaleUnconsumedEvent_soANewLoginIsNotSignedOut() = runBlocking {
        SessionManager.notifySessionExpired()
        SessionManager.notifyPasswordChangeRequired()
        SessionManager.clearPendingEvents() // what AuthRepository.login does on success
        assertNull(withTimeoutOrNull(200) { SessionManager.sessionExpiredEvent.first() })
        assertNull(withTimeoutOrNull(200) { SessionManager.passwordChangeRequiredEvent.first() })
    }

    @Test
    fun passwordChangeRequired_isAlsoOneShot() = runBlocking {
        SessionManager.notifyPasswordChangeRequired()
        assertNotNull(withTimeoutOrNull(1000) { SessionManager.passwordChangeRequiredEvent.first() })
        assertNull(withTimeoutOrNull(200) { SessionManager.passwordChangeRequiredEvent.first() })
    }

    @Test
    fun deepLink_consumeReturnsOnce() {
        SessionManager.setPendingDeepLink("visit-1")
        assertEquals("visit-1", SessionManager.consumePendingDeepLink())
        assertNull(SessionManager.consumePendingDeepLink())
    }
}
