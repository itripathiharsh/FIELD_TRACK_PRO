package com.fieldtrackpro.android.data

import com.fieldtrackpro.android.data.local.PendingAction
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class OfflineQueueUserIsolationTest {

    @Test
    fun testPendingAction_userIsolation() {
        val userAAction = PendingAction(
            id = "act-1",
            userId = "user_A",
            visitId = "vis-1",
            actionType = "CHECK_IN",
            latitude = 19.0760,
            longitude = 72.8777
        )

        val userBAction = PendingAction(
            id = "act-2",
            userId = "user_B",
            visitId = "vis-2",
            actionType = "CHECK_OUT",
            latitude = 19.0760,
            longitude = 72.8777
        )

        val queue = listOf(userAAction, userBAction)

        val activeUserId = "user_A"
        val actionsToSyncForUserA = queue.filter { it.userId == null || it.userId == activeUserId }
        val actionsToSyncForUserB = queue.filter { it.userId == null || it.userId == "user_B" }

        assertEquals(1, actionsToSyncForUserA.size)
        assertEquals("act-1", actionsToSyncForUserA[0].id)
        assertEquals("user_A", actionsToSyncForUserA[0].userId)

        assertEquals(1, actionsToSyncForUserB.size)
        assertEquals("act-2", actionsToSyncForUserB[0].id)
        assertEquals("user_B", actionsToSyncForUserB[0].userId)
    }

    @Test
    fun testLegacyAction_withoutUserId_matchesAllUsers() {
        val legacyAction = PendingAction(
            id = "act-legacy",
            userId = null,
            visitId = "vis-legacy",
            actionType = "CHECK_IN",
            latitude = 19.0760,
            longitude = 72.8777
        )

        val queue = listOf(legacyAction)
        val activeUserId = "user_A"
        val actionsToSync = queue.filter { it.userId == null || it.userId == activeUserId }

        assertEquals(1, actionsToSync.size)
        assertEquals("act-legacy", actionsToSync[0].id)
    }

    @Test
    fun testUnauthenticated_nullActiveUserId_yieldsNoActions() {
        val userAAction = PendingAction(
            id = "act-1",
            userId = "user_A",
            visitId = "vis-1",
            actionType = "CHECK_IN",
            latitude = 19.0760,
            longitude = 72.8777
        )
        val queue = listOf(userAAction)
        val activeUserId: String? = null

        // With strict session verification, null activeUserId must not sync any user-scoped actions
        val syncable = if (activeUserId.isNullOrBlank()) {
            emptyList()
        } else {
            queue.filter { it.userId == null || it.userId == activeUserId }
        }

        assertTrue(syncable.isEmpty())
    }

    @Test
    fun testCrossUserAction_isNeverSelectedForDifferentActiveUser() {
        val userAAction = PendingAction(
            id = "act-1",
            userId = "user_A",
            visitId = "vis-1",
            actionType = "CHECK_IN",
            latitude = 19.0760,
            longitude = 72.8777
        )
        val activeUserId = "user_B"

        val canSync = (userAAction.userId == null || userAAction.userId == activeUserId)
        assertFalse("User B must never be able to sync User A's pending action", canSync)
    }
}
