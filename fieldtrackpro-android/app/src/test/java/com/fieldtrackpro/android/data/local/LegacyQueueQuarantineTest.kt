package com.fieldtrackpro.android.data.local

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LegacyQueueQuarantineTest {

    private val legacyJson = """[{"id":"old-1","visitId":"v9","actionType":"CHECK_IN","latitude":1.5,"longitude":2.5},
        {"id":"old-2","visitId":"v8","actionType":"CHECK_OUT","latitude":1.5,"longitude":2.5}]"""
    private val legacyConflictJson = """[{"id":"c-1","pendingAction":{"id":"old-3","visitId":"v7","actionType":"CHECK_IN","latitude":1.0,"longitude":2.0},
        "conflictType":"STATUS_CHANGED","message":"changed","detectedAt":1}]"""

    private fun prefsWithLegacy(conflicts: Boolean = false) = InMemorySharedPreferences().also {
        val e = it.edit().putString("pending_queue", legacyJson)
        if (conflicts) e.putString("sync_conflicts", legacyConflictJson)
        e.apply()
    }

    @Test
    fun adoptedWhenLastStoredUserIsTheLoggingInUser() {
        val m = OfflineQueueManager(prefsWithLegacy(conflicts = true), previousUserIdProvider = { "empA" })
        assertEquals(setOf("old-1", "old-2"), m.getQueueForUser("empA").map { it.id }.toSet())
        assertEquals(listOf("old-3"), m.getConflictsForUser("empA").map { it.pendingAction.id })
        assertTrue(m.getQuarantinedConflicts().isEmpty())
    }

    @Test
    fun quarantinedWhenAnotherEmployeeLogsIn_neverSyncableUnderThem() {
        val m = OfflineQueueManager(prefsWithLegacy(), previousUserIdProvider = { "empA" })
        assertTrue("B must not receive A's legacy items", m.getQueueForUser("empB").isEmpty())
        assertTrue(m.getConflictsForUser("empB").isEmpty())
        assertTrue(m.getQueue().none { it.userId == null })

        val q = m.getQuarantinedConflicts()
        assertEquals(setOf("old-1", "old-2"), q.map { it.pendingAction.id }.toSet())
        assertTrue(q.all { it.conflictType == ConflictType.UNOWNED_LEGACY })
        assertTrue(q.all { it.message.contains("Unowned legacy item") })
        assertTrue(q.all { it.pendingAction.userId == null })

        // Even the "previous" user returning later cannot pull them back into the sync queue.
        assertTrue(m.getQueueForUser("empA").isEmpty())
        assertEquals(2, m.getQuarantinedConflicts().size)
    }

    @Test
    fun quarantinedWhenNoPreviousUserIsKnown() {
        val m = OfflineQueueManager(prefsWithLegacy())
        assertTrue(m.getQueueForUser("empA").isEmpty())
        assertEquals(2, m.getQuarantinedConflicts().size)
    }

    @Test
    fun quarantineIsIdempotentAndDiscardable() {
        val m = OfflineQueueManager(prefsWithLegacy(), previousUserIdProvider = { null })
        m.getQueueForUser("empB")
        m.getQueueForUser("empB")
        assertEquals(2, m.getQuarantinedConflicts().size)
        m.removeConflict(m.getQuarantinedConflicts().first().id)
        assertEquals(1, m.getQuarantinedConflicts().size)
    }

    @Test
    fun existingOwnedEntriesAreUntouchedByQuarantine() {
        val m = OfflineQueueManager(prefsWithLegacy(), previousUserIdProvider = { "empA" })
        m.enqueueAction(PendingAction(id = "own", userId = "empB", visitId = "v1", actionType = "CHECK_IN", latitude = 0.0, longitude = 0.0))
        assertEquals(listOf("own"), m.getQueueForUser("empB").map { it.id })
    }

    // ---- TokenManager last-user tracking (injected prefs, no Android)

    @Test
    fun tokenManager_recordsLastUserOnLogoutAndUserSwitch() {
        val prefs = InMemorySharedPreferences()
        val t = TokenManager(null, prefs)
        assertNull(t.getLastUserId())
        t.saveUserProfile("A", null, "EMPLOYEE", id = "empA")
        assertNull("first ever login: no previous user", t.getLastUserId())
        t.saveUserProfile("A", null, "EMPLOYEE", id = "empA")
        assertNull("same-user refresh is not a switch", t.getLastUserId())
        t.clear()
        assertEquals("empA", t.getLastUserId())
        assertNull(t.getUserId())
        t.saveUserProfile("B", null, "EMPLOYEE", id = "empB")
        assertEquals("empA", t.getLastUserId())
        t.saveUserProfile("B", null, "EMPLOYEE", id = "empB")
        assertEquals("a refresh by B must not make B 'previous'", "empA", t.getLastUserId())
        t.saveUserProfile("C", null, "EMPLOYEE", id = "empC")
        assertEquals("empB", t.getLastUserId())
    }

    @Test
    fun endToEnd_sameUserRelogin_adopts_otherUser_quarantines() {
        val prefs = InMemorySharedPreferences()
        val t = TokenManager(null, prefs)
        t.saveUserProfile("A", null, "EMPLOYEE", id = "empA")
        t.clear() // A logs out; legacy items remain unowned in the queue
        val queuePrefs = prefsWithLegacy()
        val m = OfflineQueueManager(queuePrefs, previousUserIdProvider = { t.getLastUserId() })
        t.saveUserProfile("B", null, "EMPLOYEE", id = "empB")
        assertTrue(m.getQueueForUser("empB").isEmpty())
        assertEquals(2, m.getQuarantinedConflicts().size)

        val queuePrefs2 = prefsWithLegacy()
        val t2 = TokenManager(null, InMemorySharedPreferences())
        t2.saveUserProfile("A", null, "EMPLOYEE", id = "empA")
        t2.clear()
        t2.saveUserProfile("A", null, "EMPLOYEE", id = "empA")
        val m2 = OfflineQueueManager(queuePrefs2, previousUserIdProvider = { t2.getLastUserId() })
        assertEquals(2, m2.getQueueForUser("empA").size)
    }

    // ---- Active-session upgrade migration

    @Test
    fun updateWhileLoggedIn_adoptsForCurrentUser_andSchedulesSync_once() {
        var syncs = 0
        val m = OfflineQueueManager(prefsWithLegacy(conflicts = true), onActionEnqueued = { syncs++ })
        assertEquals(3, m.migrateLegacyForActiveSession("empA"))
        assertEquals(1, syncs)
        assertEquals(setOf("old-1", "old-2"), m.getQueueForUser("empA").map { it.id }.toSet())
        assertEquals(listOf("old-3"), m.getConflictsForUser("empA").map { it.pendingAction.id })
        assertTrue(m.getQuarantinedConflicts().isEmpty())
        // once per install: second run and other users do nothing
        assertEquals(0, m.migrateLegacyForActiveSession("empB"))
        assertEquals(1, syncs)
        assertTrue(m.getQueueForUser("empB").isEmpty())
    }

    @Test
    fun loggedInAtUpdate_thenALogsOutAndBLogsIn_bNeverGetsAEntries() {
        val t = TokenManager(null, InMemorySharedPreferences())
        t.saveTokens("acc", "ref")
        t.saveUserProfile("A", null, "EMPLOYEE", id = "empA")
        assertEquals("empA", t.getActiveSessionUserId())
        val m = OfflineQueueManager(prefsWithLegacy(), previousUserIdProvider = { t.getLastUserId() })
        m.migrateLegacyForActiveSession(t.getActiveSessionUserId())
        t.clear()
        t.saveTokens("acc2", "ref2")
        t.saveUserProfile("B", null, "EMPLOYEE", id = "empB")
        assertEquals("empA", t.getLastUserId())
        assertTrue(m.getQueueForUser("empB").isEmpty())
        assertTrue(m.getQuarantinedConflicts().isEmpty())
        assertEquals(setOf("old-1", "old-2"), m.getQueueForUser("empA").map { it.id }.toSet())
    }

    @Test
    fun noSessionAndNoLastUser_staysQuarantined() {
        val t = TokenManager(null, InMemorySharedPreferences())
        assertNull(t.getActiveSessionUserId())
        val m = OfflineQueueManager(prefsWithLegacy(), previousUserIdProvider = { t.getLastUserId() })
        assertEquals(0, m.migrateLegacyForActiveSession(t.getActiveSessionUserId()))
        assertTrue(m.getQueueForUser("empA").isEmpty())
        assertEquals(2, m.getQuarantinedConflicts().size)
    }

    @Test
    fun differentUserAfterLogoutAtStartup_quarantines_evenWithLastSignedInTracking() {
        val t = TokenManager(null, InMemorySharedPreferences())
        t.saveTokens("a", "r")
        t.saveUserProfile("A", null, "EMPLOYEE", id = "empA")
        t.clear()
        assertNull(t.getActiveSessionUserId())
        assertEquals("empA", t.getLastSignedInUserId())
        val m = OfflineQueueManager(prefsWithLegacy(), previousUserIdProvider = { t.getLastUserId() })
        m.migrateLegacyForActiveSession(t.getActiveSessionUserId())
        t.saveTokens("b", "r")
        t.saveUserProfile("B", null, "EMPLOYEE", id = "empB")
        assertTrue(m.getQueueForUser("empB").isEmpty())
        assertEquals(2, m.getQuarantinedConflicts().size)
    }

    @Test
    fun legacyJsonWithoutUserIdOrNewFields_stillParses() {
        val m = OfflineQueueManager(prefsWithLegacy())
        val q = m.getQueue()
        assertEquals(2, q.size)
        assertTrue(q.all { it.userId == null && it.paymentPayload == null && !it.isMockLocation })
    }

    // ---- LogoutPolicy

    @Test
    fun logoutPolicy_countsAndNamesPayments() {
        val items = listOf(
            PendingAction(id = "1", userId = "u", visitId = "v", actionType = "CHECK_IN", latitude = 0.0, longitude = 0.0),
            PendingAction(id = "2", userId = "u", visitId = "v", actionType = PendingAction.TYPE_PAYMENT_CREATE, latitude = 0.0, longitude = 0.0),
            PendingAction(id = "3", userId = "u", visitId = "v", actionType = PendingAction.TYPE_PAYMENT_CREATE, latitude = 0.0, longitude = 0.0)
        )
        val d = LogoutPolicy.decide(items) as LogoutDecision.ConfirmUnsynced
        assertEquals(3, d.count)
        assertEquals("check-ins, payments", d.description)
        assertEquals(
            "You have 3 unsynced items (check-ins, payments). Sync now before logging out?",
            LogoutPolicy.logoutWarning(d.count, d.description)
        )
    }
}
