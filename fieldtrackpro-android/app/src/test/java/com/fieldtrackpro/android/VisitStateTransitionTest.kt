package com.fieldtrackpro.android

import com.fieldtrackpro.android.data.model.VisitDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class VisitStateTransitionTest {

    private fun createVisit(status: String): VisitDto {
        return VisitDto(
            id = "v123",
            customerId = "c456",
            employeeId = "e789",
            scheduledAt = "2026-01-01T09:00:00",
            status = status
        )
    }

    @Test
    fun pendingVisit_canCheckIn() {
        val visit = createVisit("PENDING")
        assertTrue("PENDING visit should allow check-in", visit.canCheckIn)
    }

    @Test
    fun pendingVisit_canCheckOut() {
        val visit = createVisit("PENDING")
        assertFalse("PENDING visit should NOT allow check-out", visit.canCheckOut)
    }

    @Test
    fun pendingVisit_isPending() {
        val visit = createVisit("PENDING")
        assertTrue("PENDING visit should report isPending", visit.isPending)
        assertFalse("PENDING visit should NOT report isInProgress", visit.isInProgress)
        assertFalse("PENDING visit should NOT report isComplete", visit.isComplete)
    }

    @Test
    fun inProgressVisit_canCheckOut() {
        val visit = createVisit("IN_PROGRESS")
        assertTrue("IN_PROGRESS visit should allow check-out", visit.canCheckOut)
    }

    @Test
    fun inProgressVisit_cannotCheckIn() {
        val visit = createVisit("IN_PROGRESS")
        assertFalse("IN_PROGRESS visit should NOT allow check-in", visit.canCheckIn)
    }

    @Test
    fun inProgressVisit_isInProgress() {
        val visit = createVisit("IN_PROGRESS")
        assertTrue("IN_PROGRESS visit should report isInProgress", visit.isInProgress)
        assertFalse("IN_PROGRESS visit should NOT report isPending", visit.isPending)
        assertFalse("IN_PROGRESS visit should NOT report isComplete", visit.isComplete)
    }

    @Test
    fun completedVisit_cannotCheckIn() {
        val visit = createVisit("COMPLETED")
        assertFalse("COMPLETED visit should NOT allow check-in", visit.canCheckIn)
    }

    @Test
    fun completedVisit_cannotCheckOut() {
        val visit = createVisit("COMPLETED")
        assertFalse("COMPLETED visit should NOT allow check-out", visit.canCheckOut)
    }

    @Test
    fun completedVisit_isComplete() {
        val visit = createVisit("COMPLETED")
        assertTrue("COMPLETED visit should report isComplete", visit.isComplete)
        assertFalse("COMPLETED visit should NOT report isPending", visit.isPending)
        assertFalse("COMPLETED visit should NOT report isInProgress", visit.isInProgress)
    }

    @Test
    fun flaggedVisit_canCheckIn() {
        val visit = createVisit("FLAGGED")
        assertTrue("FLAGGED visit should allow check-in", visit.canCheckIn)
    }

    @Test
    fun flaggedVisit_canCheckOut() {
        val visit = createVisit("FLAGGED")
        assertTrue("FLAGGED visit should allow check-out", visit.canCheckOut)
    }

    @Test
    fun missedVisit_cannotCheckIn() {
        val visit = createVisit("MISSED")
        assertFalse("MISSED visit should NOT allow check-in", visit.canCheckIn)
    }

    @Test
    fun missedVisit_cannotCheckOut() {
        val visit = createVisit("MISSED")
        assertFalse("MISSED visit should NOT allow check-out", visit.canCheckOut)
    }

    @Test
    fun stateTransitions_validPaths() {
        assertTrue("PENDING should allow check-in", createVisit("PENDING").canCheckIn)
        assertTrue("FLAGGED should allow check-in", createVisit("FLAGGED").canCheckIn)
        assertTrue("IN_PROGRESS should allow check-out", createVisit("IN_PROGRESS").canCheckOut)
        assertTrue("FLAGGED should allow check-out", createVisit("FLAGGED").canCheckOut)
    }

    @Test
    fun stateTransitions_invalidPaths() {
        assertFalse("COMPLETED cannot check-in", createVisit("COMPLETED").canCheckIn)
        assertFalse("COMPLETED cannot check-out", createVisit("COMPLETED").canCheckOut)
        assertFalse("PENDING cannot check-out", createVisit("PENDING").canCheckOut)
        assertFalse("MISSED cannot check-in", createVisit("MISSED").canCheckIn)
        assertFalse("MISSED cannot check-out", createVisit("MISSED").canCheckOut)
    }
}
