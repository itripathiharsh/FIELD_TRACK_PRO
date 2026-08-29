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

    companion object {
        private const val TAG = "TransientRetry"
    }

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
                    Log.w(TAG, "Transient HTTP ${response.code} on ${request.url}, retrying attempt $attempt after ${backoffMs}ms")
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
                if (isIdempotent && attempt < maxRetries) {
                    attempt++
                    Log.w(TAG, "Network IOException on ${request.url}, retrying attempt $attempt after ${backoffMs}ms: ${e.message}")
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
}
