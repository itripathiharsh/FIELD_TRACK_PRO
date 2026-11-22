package com.fieldtrackpro.android.data.remote

import android.util.Log
import okhttp3.Interceptor
import okhttp3.Response
import java.io.IOException

/**
 * Transient error retry interceptor with exponential backoff.
 *
 * APP-API-004:
 * - Retries transient gateway/server errors (502, 503, 504) and IOExceptions.
 * - Restricts retries to idempotent HTTP methods (GET, HEAD, OPTIONS) or requests with an Idempotency-Key header.
 * - Uses exponential backoff (e.g. 500ms, 1000ms) with max 2 retries.
 */
class TransientRetryInterceptor(
    private val maxRetries: Int = 2,
    private val initialBackoffMs: Long = 500L
) : Interceptor {


    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        val isIdempotent = request.method in listOf("GET", "HEAD", "OPTIONS") ||
            request.header("Idempotency-Key") != null ||
            request.header("X-Idempotency-Key") != null

        var attempt = 0
        var backoffMs = initialBackoffMs
        var lastException: IOException? = null

        while (true) {
            try {
                val response = chain.proceed(request)
                if (isIdempotent && attempt < maxRetries && isTransientError(response.code)) {
                    attempt++
                    Log.w(TAG, "Transient HTTP ${response.code} on ${request.url.encodedPath}, retrying attempt $attempt after ${backoffMs}ms")
                    response.close()
                    try {
                        Thread.sleep(backoffMs)
                    } catch (ie: InterruptedException) {
                        Thread.currentThread().interrupt()
                        return response
                    }
                    backoffMs *= 2
                    continue
                }
                return response
            } catch (e: IOException) {
                lastException = e
                if (isIdempotent && attempt < maxRetries && isRetryableIOException(e)) {
                    attempt++
                    Log.w(TAG, "Network IOException on ${request.url.encodedPath}, retrying attempt $attempt after ${backoffMs}ms: ${e.javaClass.simpleName}")
                    try {
                        Thread.sleep(backoffMs)
                    } catch (ie: InterruptedException) {
                        Thread.currentThread().interrupt()
                        throw e
                    }
                    backoffMs *= 2
                } else {
                    throw e
                }
            }
        }
    }

    private fun isTransientError(code: Int): Boolean = code in listOf(502, 503, 504)

    companion object {
        private const val TAG = "TransientRetry"

        /**
         * Retry only failures where a second attempt can plausibly succeed quickly (connection refused/reset, TLS
         * hiccup). A read timeout already cost the full timeout and usually means a slow server, and an unknown host
         * means no network at all: retrying those only made the user wait up to ~46 s before seeing an error.
         */
        fun isRetryableIOException(e: IOException): Boolean = when (e) {
            is java.net.SocketTimeoutException -> false
            is java.net.UnknownHostException -> false
            is java.io.InterruptedIOException -> false
            else -> true
        }
    }
}
