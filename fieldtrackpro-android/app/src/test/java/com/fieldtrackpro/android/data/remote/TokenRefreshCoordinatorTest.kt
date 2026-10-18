package com.fieldtrackpro.android.data.remote

import com.fieldtrackpro.android.utils.SessionManager
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * TokenRefreshCoordinator is the shared lock between TokenAuthenticator (401-triggered) and any
 * other caller that proactively verifies/refreshes a session - AuthRepository.refreshSession(),
 * which SplashScreen calls on cold start. Before this existed, SplashScreen made its own
 * unsynchronized refresh call: a cold start racing a concurrent 401-triggered refresh (e.g. from
 * a notification sync kicked off in the same onCreate) could fire two independent refreshes of
 * the SAME refresh token - exactly the pattern the backend's reuse detection treats as theft.
 */
class TokenRefreshCoordinatorTest {

    private lateinit var server: SimpleHttpServer

    @Before
    fun setup() {
        SessionManager.reset()
        server = SimpleHttpServer()
    }

    @After
    fun tearDown() {
        server.close()
        SessionManager.reset()
    }

    private fun baseUrl(): String = "http://127.0.0.1:${server.port}/"

    @Test
    fun refresh_success_savesTokens() {
        server.enqueueResponse(200, """{"access_token":"new_access","refresh_token":"new_refresh","token_type":"bearer"}""")
        val tokenManager = FakeTokenManager(accessToken = "old_access", refreshToken = "old_refresh")

        val outcome = TokenRefreshCoordinator.refresh(tokenManager, baseUrl())

        assertTrue(outcome is TokenRefreshCoordinator.RefreshOutcome.Success)
        assertEquals("new_access", tokenManager.getAccessToken())
        assertEquals("new_refresh", tokenManager.getRefreshToken())
    }

    @Test
    fun refresh_rejected_clearsSession() {
        server.enqueueResponse(401, """{"detail":"invalid"}""")
        val tokenManager = FakeTokenManager(accessToken = "old_access", refreshToken = "old_refresh")

        val outcome = TokenRefreshCoordinator.refresh(tokenManager, baseUrl())

        assertTrue(outcome is TokenRefreshCoordinator.RefreshOutcome.Rejected)
        assertNull(tokenManager.getAccessToken())
    }

    @Test
    fun refresh_transient_keepsSession() {
        server.enqueueResponse(502, """{"detail":"bad gateway"}""")
        val tokenManager = FakeTokenManager(accessToken = "old_access", refreshToken = "old_refresh")

        val outcome = TokenRefreshCoordinator.refresh(tokenManager, baseUrl())

        assertTrue(outcome is TokenRefreshCoordinator.RefreshOutcome.Transient)
        assertEquals("Session must be kept on a transient failure", "old_access", tokenManager.getAccessToken())
        assertEquals("old_refresh", tokenManager.getRefreshToken())
    }

    @Test
    fun refresh_noToken_doesNotHitNetwork() {
        val tokenManager = FakeTokenManager(accessToken = null, refreshToken = null)

        val outcome = TokenRefreshCoordinator.refresh(tokenManager, baseUrl())

        assertTrue(outcome is TokenRefreshCoordinator.RefreshOutcome.NoToken)
        assertEquals(0, server.requestCount.get())
    }

    @Test
    fun concurrentCallers_bothComplete_withoutCorruptingSessionState() {
        // Simulates SplashScreen (AuthRepository.refreshSession()) racing some OTHER caller of
        // TokenRefreshCoordinator directly - not going through TokenAuthenticator at all - on the
        // same refresh token. The lock means they're serialised (not concurrent on the network
        // call), so the server always has a response ready for whichever one goes second.
        server.enqueueResponse(200, """{"access_token":"a1","refresh_token":"r1","token_type":"bearer"}""")
        server.enqueueResponse(200, """{"access_token":"a2","refresh_token":"r2","token_type":"bearer"}""")
        val tokenManager = FakeTokenManager(accessToken = "old_access", refreshToken = "old_refresh")

        val executor = Executors.newFixedThreadPool(2)
        val latch = CountDownLatch(2)
        val outcomes = mutableListOf<TokenRefreshCoordinator.RefreshOutcome>()

        repeat(2) {
            executor.submit {
                val outcome = TokenRefreshCoordinator.refresh(tokenManager, baseUrl())
                synchronized(outcomes) { outcomes.add(outcome) }
                latch.countDown()
            }
        }

        assertTrue("Both callers must finish", latch.await(5, TimeUnit.SECONDS))
        executor.shutdown()

        assertEquals(2, outcomes.size)
        assertTrue("Both must succeed (lock serialises, doesn't fail either)", outcomes.all { it is TokenRefreshCoordinator.RefreshOutcome.Success })
        assertEquals(2, server.requestCount.get())
        // Final state is whichever response landed last - never null/partial/corrupted.
        assertNotNull(tokenManager.getAccessToken())
        assertNotNull(tokenManager.getRefreshToken())
        assertTrue(tokenManager.getAccessToken() in setOf("a1", "a2"))
    }
}
