package com.fieldtrackpro.android.data.remote

import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.utils.SessionManager
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeoutOrNull
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

/**
 * Fake in-memory TokenManager for unit testing without Android context.
 */
class FakeTokenManager(
    private var accessToken: String? = null,
    private var refreshToken: String? = null
) : TokenManager(null) {
    override fun getAccessToken(): String? = accessToken
    override fun getRefreshToken(): String? = refreshToken
    override fun saveTokens(access: String, refresh: String) {
        accessToken = access
        refreshToken = refresh
    }
    override fun clear() {
        accessToken = null
        refreshToken = null
    }
}

/**
 * Simple embedded HTTP server backed by standard java.net.ServerSocket.
 */
class SimpleHttpServer : AutoCloseable {
    private val serverSocket = ServerSocket(0)
    val port: Int = serverSocket.localPort
    @Volatile private var isRunning = true
    private val responses = mutableListOf<Pair<Int, String>>()
    val requestCount = AtomicInteger(0)

    init {
        Thread {
            while (isRunning) {
                try {
                    val clientSocket: Socket = serverSocket.accept()
                    requestCount.incrementAndGet()
                    handleClient(clientSocket)
                } catch (e: Exception) {
                    if (!isRunning) break
                }
            }
        }.apply { isDaemon = true; start() }
    }

    fun enqueueResponse(statusCode: Int, body: String) {
        synchronized(responses) {
            responses.add(statusCode to body)
        }
    }

    private fun handleClient(socket: Socket) {
        Thread {
            try {
                val reader = BufferedReader(InputStreamReader(socket.getInputStream()))
                // Read request line and headers
                var line: String? = reader.readLine()
                var contentLength = 0
                while (!line.isNullOrEmpty()) {
                    if (line.lowercase().startsWith("content-length:")) {
                        contentLength = line.substringAfter(":").trim().toIntOrNull() ?: 0
                    }
                    line = reader.readLine()
                }
                // Discard request body if any
                if (contentLength > 0) {
                    reader.read(CharArray(contentLength))
                }

                val (statusCode, body) = synchronized(responses) {
                    if (responses.isNotEmpty()) responses.removeAt(0)
                    else 200 to "{}"
                }

                val statusText = if (statusCode == 200) "OK" else if (statusCode == 401) "Unauthorized" else "Error"
                val bodyBytes = body.toByteArray(Charsets.UTF_8)

                val writer = OutputStreamWriter(socket.getOutputStream(), Charsets.UTF_8)
                writer.write("HTTP/1.1 $statusCode $statusText\r\n")
                writer.write("Content-Type: application/json; charset=utf-8\r\n")
                writer.write("Content-Length: ${bodyBytes.size}\r\n")
                writer.write("Connection: close\r\n\r\n")
                writer.write(body)
                writer.flush()
                socket.close()
            } catch (e: Exception) {
                try { socket.close() } catch (_: Exception) {}
            }
        }.apply { isDaemon = true; start() }
    }

    override fun close() {
        isRunning = false
        try { serverSocket.close() } catch (_: Exception) {}
    }
}

/**
 * Unit tests for Global 401 Token Refresh (APP-API-001).
 */
class TokenAuthenticatorTest {

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

    private fun createFakeResponse(request: Request, code: Int = 401, priorResponse: Response? = null): Response {
        val builder = Response.Builder()
            .request(request)
            .protocol(Protocol.HTTP_1_1)
            .code(code)
            .message(if (code == 401) "Unauthorized" else "OK")
        if (priorResponse != null) {
            builder.priorResponse(priorResponse)
        }
        return builder.build()
    }

    @Test
    fun expiredToken_refreshesAndReturnsRetryRequest() {
        server.enqueueResponse(
            200,
            """{"access_token":"fresh_access_token","refresh_token":"fresh_refresh_token","token_type":"bearer"}"""
        )

        val tokenManager = FakeTokenManager(accessToken = "expired_token", refreshToken = "valid_refresh_token")
        val authenticator = TokenAuthenticator(tokenManager) { baseUrl() }

        val originalRequest = Request.Builder()
            .url("${baseUrl()}api/v1/visits")
            .header("Authorization", "Bearer expired_token")
            .build()

        val response = createFakeResponse(originalRequest, 401)
        val retryRequest = authenticator.authenticate(null, response)

        assertNotNull("Retry request should be generated", retryRequest)
        assertEquals("Bearer fresh_access_token", retryRequest?.header("Authorization"))
        assertEquals("fresh_access_token", tokenManager.getAccessToken())
        assertEquals("fresh_refresh_token", tokenManager.getRefreshToken())
    }

    @Test
    fun refreshFailure_clearsSessionAndEmitsSessionExpired() = runBlocking {
        server.enqueueResponse(
            401,
            """{"error":{"code":"UNAUTHORIZED","message":"Invalid refresh token"}}"""
        )

        val tokenManager = FakeTokenManager(accessToken = "expired_token", refreshToken = "invalid_refresh_token")
        val authenticator = TokenAuthenticator(tokenManager) { baseUrl() }

        val originalRequest = Request.Builder()
            .url("${baseUrl()}api/v1/visits")
            .header("Authorization", "Bearer expired_token")
            .build()

        val response = createFakeResponse(originalRequest, 401)
        val retryRequest = authenticator.authenticate(null, response)

        assertNull("Retry request should be null on refresh failure", retryRequest)
        assertNull("Access token should be cleared", tokenManager.getAccessToken())

        // Verify session expired event was emitted
        val eventReceived = withTimeoutOrNull(1000) {
            SessionManager.sessionExpiredEvent.first()
        }
        assertNotNull("Session expired event must be dispatched", eventReceived)
    }

    @Test
    fun retryReturning401_doesNotLoop() {
        val tokenManager = FakeTokenManager(accessToken = "fresh_token", refreshToken = "valid_refresh")
        val authenticator = TokenAuthenticator(tokenManager) { baseUrl() }

        val originalRequest = Request.Builder()
            .url("${baseUrl()}api/v1/visits")
            .header("Authorization", "Bearer old_token")
            .build()

        val firstResponse = createFakeResponse(originalRequest, 401)
        val retriedResponse = createFakeResponse(originalRequest, 401, priorResponse = firstResponse)

        val nextRetry = authenticator.authenticate(null, retriedResponse)
        assertNull("Should abort on second consecutive 401 to prevent infinite loop", nextRetry)
    }

    @Test
    fun concurrent401s_executeSingleRefresh() {
        server.enqueueResponse(
            200,
            """{"access_token":"shared_new_token","refresh_token":"shared_new_refresh","token_type":"bearer"}"""
        )

        val tokenManager = FakeTokenManager(accessToken = "expired_token", refreshToken = "valid_refresh")
        val authenticator = TokenAuthenticator(tokenManager) { baseUrl() }

        val threadCount = 5
        val executor = Executors.newFixedThreadPool(threadCount)
        val latch = CountDownLatch(threadCount)
        val results = mutableListOf<Request?>()

        for (i in 1..threadCount) {
            executor.submit {
                val req = Request.Builder()
                    .url("${baseUrl()}api/v1/visits/$i")
                    .header("Authorization", "Bearer expired_token")
                    .build()
                val resp = createFakeResponse(req, 401)
                val retry = authenticator.authenticate(null, resp)
                synchronized(results) {
                    results.add(retry)
                }
                latch.countDown()
            }
        }

        latch.await(5, TimeUnit.SECONDS)
        executor.shutdown()

        assertEquals(threadCount, results.size)
        // All threads obtain a retry request with the new shared token
        for (res in results) {
            assertNotNull(res)
            assertEquals("Bearer shared_new_token", res?.header("Authorization"))
        }
        assertEquals(1, server.requestCount.get())
    }
}
