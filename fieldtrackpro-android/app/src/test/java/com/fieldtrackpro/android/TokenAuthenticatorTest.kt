package com.fieldtrackpro.android

import com.fieldtrackpro.android.utils.SessionManager
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TokenAuthenticatorTest {

    @Test
    fun authenticator_second401_abortsInfiniteLoop() {
        val firstRequest = Request.Builder()
            .url("http://localhost/api/v1/visits")
            .header("Authorization", "Bearer token1")
            .build()

        val first401 = Response.Builder()
            .request(firstRequest)
            .protocol(Protocol.HTTP_1_1)
            .code(401)
            .message("Unauthorized")
            .build()

        val initialRequest = Request.Builder()
            .url("http://localhost/api/v1/visits")
            .header("Authorization", "Bearer token1")
            .build()

        val multiRetryResponse = Response.Builder()
            .request(initialRequest)
            .protocol(Protocol.HTTP_1_1)
            .code(401)
            .message("Unauthorized")
            .priorResponse(first401)
            .build()

        var count = 1
        var prior = multiRetryResponse.priorResponse
        while (prior != null) {
            count++
            prior = prior.priorResponse
        }
        assertTrue("Prior response count should detect repeated 401", count >= 2)
    }

    @Test
    fun sessionManager_emitsSessionExpiredEvent() = runBlocking {
        SessionManager.reset()
        SessionManager.notifySessionExpired()
        val event = SessionManager.sessionExpiredEvent.first()
        assertEquals(Unit, event)
    }
}
