package com.fieldtrackpro.android.data.local

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class OfflineQueuePerUserTest {

    private fun action(id: String, user: String?, visit: String = "v1", type: String = "CHECK_IN") =
        PendingAction(id = id, userId = user, visitId = visit, actionType = type, latitude = 1.0, longitude = 2.0)

    private val legacyJson = """[{"id":"old-1","visitId":"v9","actionType":"CHECK_IN","latitude":1.5,"longitude":2.5},
        {"id":"old-2","userId":"userA","visitId":"v8","actionType":"CHECK_OUT","latitude":1.5,"longitude":2.5}]"""

    @Test
    fun differentUsersNeverSeeEachOthersItems() {
        val m = OfflineQueueManager(InMemorySharedPreferences())
        m.enqueueAction(action("a1", "userA"))
        m.enqueueAction(action("b1", "userB", visit = "v2"))
        assertEquals(listOf("a1"), m.getQueueForUser("userA").map { it.id })
        assertEquals(listOf("b1"), m.getQueueForUser("userB").map { it.id })
        assertTrue(m.getQueueForUser(null).isEmpty())
        assertTrue(m.getQueueForUser(" ").isEmpty())
    }

    @Test
    fun sameVisitSameTypeFromTwoUsers_doesNotOverwrite() {
        val m = OfflineQueueManager(InMemorySharedPreferences())
        m.enqueueAction(action("a1", "userA"))
        m.enqueueAction(action("b1", "userB"))
        assertEquals(2, m.getQueue().size)
        m.enqueueAction(action("a2", "userA"))
        assertEquals(listOf("a2"), m.getQueueForUser("userA").map { it.id })
        assertEquals(listOf("b1"), m.getQueueForUser("userB").map { it.id })
    }

    @Test
    fun legacyUnownedEntries_areAdoptedOnlyByThePreviouslySignedInUser() {
        val prefs = InMemorySharedPreferences()
        prefs.edit().putString("pending_queue", legacyJson).apply()
        val m = OfflineQueueManager(prefs, previousUserIdProvider = { "userA" })
        assertEquals(setOf("old-1", "old-2"), m.getQueueForUser("userA").map { it.id }.toSet())
        // Persisted: second employee on the same phone sees nothing.
        assertTrue(m.getQueueForUser("userB").isEmpty())
        assertTrue(m.getQueue().all { it.userId == "userA" })
    }

    @Test
    fun legacyEntriesAreNotStolenFromOwnedUsers_andNotAdoptedByAStranger() {
        val prefs = InMemorySharedPreferences()
        prefs.edit().putString("pending_queue", legacyJson).apply()
        val m = OfflineQueueManager(prefs, previousUserIdProvider = { "userA" })
        // userB logs in first: the unowned entry cannot be attributed to B, so it is quarantined, not adopted.
        assertTrue(m.getQueueForUser("userB").isEmpty())
        assertEquals(listOf("old-2"), m.getQueueForUser("userA").map { it.id })
    }

    @Test
    fun clearQueueForUser_keepsOtherUsersItems() {
        val m = OfflineQueueManager(InMemorySharedPreferences())
        m.enqueueAction(action("a1", "userA"))
        m.enqueueAction(action("b1", "userB", visit = "v2"))
        m.clearQueueForUser("userA")
        assertTrue(m.getQueueForUser("userA").isEmpty())
        assertEquals(1, m.getQueueForUser("userB").size)
    }

    @Test
    fun moveToConflict_removesFromQueueAndIsPerUser() {
        val m = OfflineQueueManager(InMemorySharedPreferences())
        val a = action("a1", "userA")
        m.enqueueAction(a)
        m.enqueueAction(action("b1", "userB", visit = "v2"))
        m.moveToConflict(SyncErrorPolicy.notAvailableConflict(a))
        m.moveToConflict(SyncErrorPolicy.notAvailableConflict(a)) // idempotent, no duplicate
        assertTrue(m.getQueueForUser("userA").isEmpty())
        assertEquals(1, m.getConflictsForUser("userA").size)
        assertTrue(m.getConflictsForUser("userB").isEmpty())
        assertEquals(1, m.getQueueForUser("userB").size)
    }

    @Test
    fun logoutKeepsQueue_sameUserSeesItAgain() {
        val m = OfflineQueueManager(InMemorySharedPreferences())
        m.enqueueAction(action("a1", "userA"))
        // "Log out anyway" does not touch the queue; same user logging back in still has it.
        assertEquals(1, m.getQueueForUser("userA").size)
    }
}
