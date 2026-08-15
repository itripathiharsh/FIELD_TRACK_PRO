package com.fieldtrackpro.android.workers

/**
 * P1-6: shared classification of "is this failure worth retrying" - used by
 * both the WorkManager workers (deciding Result.retry() vs Result.failure())
 * and the ViewModels that decide whether a failed *direct* upload attempt
 * should be queued for a background retry at all. A validation/auth failure
 * will fail identically on every retry, so it is never queued; a
 * network/timeout/server error might succeed on the next attempt.
 *
 * Previously duplicated as a private fun inside each Worker; now one place
 * both the Workers and the ViewModels call.
 */
object UploadRetryPolicy {
    fun isTransientFailure(errorMessage: String): Boolean {
        val lower = errorMessage.lowercase()
        return !lower.contains("invalid") &&
            !lower.contains("unsupported") &&
            !lower.contains("too large") &&
            !lower.contains("unauthorized") &&
            !lower.contains("forbidden") &&
            !lower.contains("already exists")
    }
}
