package com.fieldtrackpro.android.data.local

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SyncConflictTest {

    @Test
    fun testSyncConflictCreation() {
        val action = PendingAction(
            visitId = "visit-123",
            actionType = "CHECK_IN",
            latitude = 12.9716,
            longitude = 77.5946
        )

        val conflict = SyncConflict(
            pendingAction = action,
            conflictType = ConflictType.STATUS_CHANGED,
            serverStatus = "COMPLETED",
            message = "Visit was already completed"
        )

        assertEquals("visit-123", conflict.pendingAction.visitId)
        assertEquals("CHECK_IN", conflict.pendingAction.actionType)
        assertEquals(ConflictType.STATUS_CHANGED, conflict.conflictType)
        assertEquals("COMPLETED", conflict.serverStatus)
        assertEquals("Visit was already completed", conflict.message)
        assertTrue(conflict.id.isNotEmpty())
        assertTrue(conflict.detectedAt > 0)
    }

    @Test
    fun testConflictTypeEnumValues() {
        val types = ConflictType.values()
        assertEquals(5, types.size)
        assertTrue(types.contains(ConflictType.STATUS_CHANGED))
        assertTrue(types.contains(ConflictType.VISIT_UNAVAILABLE))
        assertTrue(types.contains(ConflictType.GEO_VALIDATION_FAILED))
        assertTrue(types.contains(ConflictType.SERVER_REJECTED))
        assertTrue(types.contains(ConflictType.NETWORK_ERROR))
    }

    @Test
    fun testConflictWithDefaultId() {
        val action = PendingAction(
            visitId = "visit-456",
            actionType = "CHECK_OUT",
            latitude = 12.9716,
            longitude = 77.5946
        )

        val conflict = SyncConflict(
            pendingAction = action,
            conflictType = ConflictType.VISIT_UNAVAILABLE,
            serverStatus = null,
            message = "Visit was deleted"
        )

        assertTrue(conflict.id.isNotEmpty())
        assertEquals(null, conflict.serverStatus)
    }

    @Test
    fun testPendingActionCreation() {
        val action = PendingAction(
            visitId = "visit-789",
            actionType = "CHECK_IN",
            latitude = 12.9716,
            longitude = 77.5946,
            notes = "Test note"
        )

        assertEquals("visit-789", action.visitId)
        assertEquals("CHECK_IN", action.actionType)
        assertEquals(12.9716, action.latitude, 0.0001)
        assertEquals(77.5946, action.longitude, 0.0001)
        assertEquals("Test note", action.notes)
        assertTrue(action.id.isNotEmpty())
        assertTrue(action.timestamp > 0)
    }
}
