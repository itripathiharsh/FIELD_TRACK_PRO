package com.fieldtrackpro.android

import com.fieldtrackpro.android.data.model.NotificationDto
import com.fieldtrackpro.android.ui.viewmodel.NotificationState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NotificationDtoTest {

    @Test
    fun notificationDto_fields_preserved() {
        val notification = NotificationDto(
            id = "n1",
            userId = "u1",
            visitId = "v1",
            notificationType = "NEW_VISIT",
            message = "New visit assigned to you",
            isRead = false,
            sentAt = "2026-01-01T10:00:00Z"
        )

        assertEquals("n1", notification.id)
        assertEquals("u1", notification.userId)
        assertEquals("v1", notification.visitId)
        assertEquals("NEW_VISIT", notification.notificationType)
        assertEquals("New visit assigned to you", notification.message)
        assertFalse(notification.isRead)
        assertEquals("2026-01-01T10:00:00Z", notification.sentAt)
    }

    @Test
    fun notificationDto_nullVisitId_allowed() {
        val notification = NotificationDto(
            id = "n2",
            userId = "u1",
            visitId = null,
            notificationType = "REMINDER",
            message = "General reminder",
            isRead = true,
            sentAt = "2026-01-01T09:00:00Z"
        )

        assertEquals(null, notification.visitId)
        assertTrue(notification.isRead)
    }

    @Test
    fun notificationState_idle_isCorrectType() {
        val state: NotificationState = NotificationState.Idle
        assertTrue(state is NotificationState.Idle)
    }

    @Test
    fun notificationState_loading_isCorrectType() {
        val state: NotificationState = NotificationState.Loading
        assertTrue(state is NotificationState.Loading)
    }

    @Test
    fun notificationState_success_holdsItems() {
        val items = listOf(
            NotificationDto("1", "u1", null, "NEW_VISIT", "msg1", false, "2026-01-01T10:00:00Z"),
            NotificationDto("2", "u1", null, "REMINDER", "msg2", true, "2026-01-01T09:00:00Z")
        )
        val state = NotificationState.Success(items)

        assertEquals(2, state.items.size)
        assertEquals("msg1", state.items[0].message)
        assertEquals("msg2", state.items[1].message)
    }

    @Test
    fun notificationState_success_emptyList() {
        val state = NotificationState.Success(emptyList())
        assertTrue(state.items.isEmpty())
    }

    @Test
    fun notificationState_error_holdsMessage() {
        val state = NotificationState.Error("Network error")
        assertEquals("Network error", state.message)
    }

    @Test
    fun notificationDto_readState_distinct() {
        val unread = NotificationDto("1", "u1", null, "NEW_VISIT", "msg", false, "2026-01-01T10:00:00Z")
        val read = NotificationDto("2", "u1", null, "REMINDER", "msg", true, "2026-01-01T09:00:00Z")

        assertFalse("First notification should be unread", unread.isRead)
        assertTrue("Second notification should be read", read.isRead)
    }

    @Test
    fun notificationDto_types_distinct() {
        val newVisit = NotificationDto("1", "u1", "v1", "NEW_VISIT", "msg", false, "2026-01-01T10:00:00Z")
        val reminder = NotificationDto("2", "u1", null, "REMINDER", "msg", false, "2026-01-01T09:00:00Z")
        val overdue = NotificationDto("3", "u1", "v2", "OVERDUE", "msg", false, "2026-01-01T08:00:00Z")
        val completed = NotificationDto("4", "u1", "v3", "COMPLETED", "msg", false, "2026-01-01T07:00:00Z")

        assertEquals("NEW_VISIT", newVisit.notificationType)
        assertEquals("REMINDER", reminder.notificationType)
        assertEquals("OVERDUE", overdue.notificationType)
        assertEquals("COMPLETED", completed.notificationType)
    }
}
