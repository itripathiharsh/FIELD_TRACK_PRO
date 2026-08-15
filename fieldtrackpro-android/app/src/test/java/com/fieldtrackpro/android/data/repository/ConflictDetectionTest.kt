package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.local.ConflictType
import com.fieldtrackpro.android.data.local.PendingAction
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * Tests for conflict detection logic - calls VisitRepository.detectConflict/
 * detectConflictFromError directly (both exposed on the companion object for
 * exactly this reason) rather than a hand-copied duplicate of the logic.
 *
 * Note: Full integration tests require Android context and are in the androidTest source set.
 */
class ConflictDetectionTest {

    @Test
    fun testCheckInConflictWhenCompleted() {
        val action = PendingAction(visitId = "v1", actionType = "CHECK_IN", latitude = 0.0, longitude = 0.0)
        val conflict = VisitRepository.detectConflict(action, "COMPLETED")
        assertNotNull(conflict)
        assertEquals(ConflictType.STATUS_CHANGED, conflict!!.conflictType)
        assertEquals("COMPLETED", conflict.serverStatus)
    }

    @Test
    fun testCheckOutConflictWhenCompleted() {
        val action = PendingAction(visitId = "v1", actionType = "CHECK_OUT", latitude = 0.0, longitude = 0.0)
        val conflict = VisitRepository.detectConflict(action, "COMPLETED")
        assertNotNull(conflict)
        assertEquals(ConflictType.STATUS_CHANGED, conflict!!.conflictType)
    }

    @Test
    fun testCheckInConflictWhenMissed() {
        val action = PendingAction(visitId = "v1", actionType = "CHECK_IN", latitude = 0.0, longitude = 0.0)
        val conflict = VisitRepository.detectConflict(action, "MISSED")
        assertNotNull(conflict)
        assertEquals(ConflictType.STATUS_CHANGED, conflict!!.conflictType)
    }

    @Test
    fun testCheckOutConflictWhenPending() {
        val action = PendingAction(visitId = "v1", actionType = "CHECK_OUT", latitude = 0.0, longitude = 0.0)
        val conflict = VisitRepository.detectConflict(action, "PENDING")
        assertNotNull(conflict)
        assertEquals(ConflictType.STATUS_CHANGED, conflict!!.conflictType)
    }

    @Test
    fun testNoConflictForValidCheckIn() {
        val action = PendingAction(visitId = "v1", actionType = "CHECK_IN", latitude = 0.0, longitude = 0.0)
        val conflict = VisitRepository.detectConflict(action, "PENDING")
        assertNull(conflict)
    }

    @Test
    fun testNoConflictForValidCheckOut() {
        val action = PendingAction(visitId = "v1", actionType = "CHECK_OUT", latitude = 0.0, longitude = 0.0)
        val conflict = VisitRepository.detectConflict(action, "IN_PROGRESS")
        assertNull(conflict)
    }

    @Test
    fun testNoConflictWhenServerStatusNull() {
        val action = PendingAction(visitId = "v1", actionType = "CHECK_IN", latitude = 0.0, longitude = 0.0)
        val conflict = VisitRepository.detectConflict(action, null)
        assertNull(conflict)
    }

    @Test
    fun testNoConflictForInProgressCheckIn() {
        val action = PendingAction(visitId = "v1", actionType = "CHECK_IN", latitude = 0.0, longitude = 0.0)
        val conflict = VisitRepository.detectConflict(action, "IN_PROGRESS")
        assertNull(conflict)
    }

    // -- detectConflictFromError -------------------------------------------

    @Test
    fun testGeoValidationFailedConflictFromStaleOrOutOfRangeCheckIn() {
        val action = PendingAction(visitId = "v1", actionType = "CHECK_IN", latitude = 0.0, longitude = 0.0)
        val errorMessage = "Check-in rejected (422): {\"error\":{\"code\":\"GEO_VERIFICATION_FAILED\",\"message\":\"GPS fix is too old\"}}"
        val conflict = VisitRepository.detectConflictFromError(action, errorMessage, 422)
        assertNotNull(conflict)
        assertEquals(ConflictType.GEO_VALIDATION_FAILED, conflict!!.conflictType)
        assertEquals(errorMessage, conflict.message)
    }

    @Test
    fun testServerRejectedConflictOn409() {
        val action = PendingAction(visitId = "v1", actionType = "CHECK_IN", latitude = 0.0, longitude = 0.0)
        val conflict = VisitRepository.detectConflictFromError(action, "duplicate submission", 409)
        assertNotNull(conflict)
        assertEquals(ConflictType.SERVER_REJECTED, conflict!!.conflictType)
    }

    @Test
    fun testVisitUnavailableConflictOn404() {
        val action = PendingAction(visitId = "v1", actionType = "CHECK_IN", latitude = 0.0, longitude = 0.0)
        val conflict = VisitRepository.detectConflictFromError(action, "Visit not found", 404)
        assertNotNull(conflict)
        assertEquals(ConflictType.VISIT_UNAVAILABLE, conflict!!.conflictType)
    }

    @Test
    fun testNetworkErrorConflictOn5xx() {
        val action = PendingAction(visitId = "v1", actionType = "CHECK_IN", latitude = 0.0, longitude = 0.0)
        val conflict = VisitRepository.detectConflictFromError(action, "Internal server error", 500)
        assertNotNull(conflict)
        assertEquals(ConflictType.NETWORK_ERROR, conflict!!.conflictType)
    }

    @Test
    fun testNoConflictFromErrorWhenMessageIsNull() {
        val action = PendingAction(visitId = "v1", actionType = "CHECK_IN", latitude = 0.0, longitude = 0.0)
        val conflict = VisitRepository.detectConflictFromError(action, null, 422)
        assertNull(conflict)
    }

    @Test
    fun testNoConflictFromErrorForAnUnrecognisedFailure() {
        val action = PendingAction(visitId = "v1", actionType = "CHECK_IN", latitude = 0.0, longitude = 0.0)
        // A 422 that is NOT the geo-verification failure (e.g. a plain
        // validation error) should not be miscategorised as GEO_VALIDATION_FAILED.
        val conflict = VisitRepository.detectConflictFromError(action, "Some other validation error", 422)
        assertNull(conflict)
    }
}
