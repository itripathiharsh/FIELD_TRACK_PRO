package com.fieldtrackpro.android.workers

import com.fieldtrackpro.android.data.local.ConflictType
import com.fieldtrackpro.android.data.local.PendingAction
import com.fieldtrackpro.android.data.local.SyncErrorClass
import com.fieldtrackpro.android.data.local.SyncErrorPolicy
import com.fieldtrackpro.android.data.model.SyncResult
import com.fieldtrackpro.android.data.remote.ApiErrorParser
import com.fieldtrackpro.android.data.remote.HttpErrors
import com.fieldtrackpro.android.data.repository.VisitRepository
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test

class SyncNotFoundClassificationTest {

    private val action = PendingAction(id = "x", userId = "u", visitId = "v", actionType = "CHECK_IN", latitude = 0.0, longitude = 0.0)

    @Test
    fun classify_byHttpCode() {
        assertEquals(SyncErrorClass.AUTH_EXPIRED, SyncErrorPolicy.classify(401))
        assertEquals(SyncErrorClass.NOT_AVAILABLE, SyncErrorPolicy.classify(404))
        assertEquals(SyncErrorClass.RETRYABLE, SyncErrorPolicy.classify(null))
        assertEquals(SyncErrorClass.RETRYABLE, SyncErrorPolicy.classify(503))
        assertEquals(SyncErrorClass.REJECTED, SyncErrorPolicy.classify(422))
        assertEquals(SyncErrorClass.REJECTED, SyncErrorPolicy.classify(403))
    }

    @Test
    fun notFound_isConflictNotRetryable() {
        val conflict = VisitRepository.detectConflictFromError(action, "Not Found", 404)
        assertNotNull(conflict)
        assertEquals(ConflictType.VISIT_UNAVAILABLE, conflict!!.conflictType)
        assertEquals(SyncErrorPolicy.NOT_AVAILABLE_MESSAGE, conflict.message)
        // A 404 must not count as a retryable failure: worker reports SUCCESS (conflict surfaced, no retry loop).
        val result = SyncResult(syncedCount = 0, conflicts = listOf(conflict), retryableFailures = 0)
        assertEquals(OfflineSyncWorker.Outcome.SUCCESS, OfflineSyncWorker.outcomeFor(result))
    }

    @Test
    fun notFoundBeatsConflictKeywordInMessage() {
        val conflict = VisitRepository.detectConflictFromError(action, "conflict: record missing", 404)
        assertEquals(ConflictType.VISIT_UNAVAILABLE, conflict!!.conflictType)
    }

    @Test
    fun friendly404Messages() {
        assertEquals(HttpErrors.NOT_AVAILABLE_MESSAGE, HttpErrors.message(404, "Failed to load visit (404)"))
        assertEquals("Failed to load visit (500)", HttpErrors.message(500, "Failed to load visit (500)"))
        assertEquals(HttpErrors.NOT_AVAILABLE_MESSAGE, ApiErrorParser.parse(404, "{\"error\":{\"message\":\"Not Found\"}}").message)
    }
}
