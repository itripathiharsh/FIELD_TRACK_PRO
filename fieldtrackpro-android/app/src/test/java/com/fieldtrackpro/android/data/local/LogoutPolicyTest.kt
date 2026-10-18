package com.fieldtrackpro.android.data.local

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class LogoutPolicyTest {

    private fun a(type: String, id: String = type) =
        PendingAction(id = id, userId = "u", visitId = "v-$id", actionType = type, latitude = 0.0, longitude = 0.0)

    @Test
    fun emptyQueue_proceedsImmediately() {
        assertEquals(LogoutDecision.Proceed, LogoutPolicy.decide(emptyList()))
    }

    @Test
    fun pendingItems_requireConfirmationWithCountAndKinds() {
        val d = LogoutPolicy.decide(listOf(a("CHECK_IN", "1"), a("CHECK_IN", "2"), a("CHECK_OUT", "3")))
        d as LogoutDecision.ConfirmUnsynced
        assertEquals(3, d.count)
        assertEquals("check-ins, check-outs", d.description)
        assertEquals(
            "You have 3 unsynced items (check-ins, check-outs). Sync now before logging out?",
            LogoutPolicy.logoutWarning(d.count, d.description)
        )
    }

    @Test
    fun singularWording() {
        assertTrue(LogoutPolicy.logoutWarning(1, "check-ins").startsWith("You have 1 unsynced item ("))
    }

    @Test
    fun afterSync_zeroLeft_allowsLogout() {
        assertEquals(SyncBeforeLogoutResult.AllSynced, LogoutPolicy.afterSync(emptyList()))
    }

    @Test
    fun afterSync_someLeft_reportsRemainingAndLetsUserChoose() {
        val r = LogoutPolicy.afterSync(listOf(a("START_DAY")))
        r as SyncBeforeLogoutResult.StillPending
        assertEquals(1, r.remaining)
        assertEquals("start-of-day records", r.description)
        assertTrue(LogoutPolicy.stillPendingMessage(2).startsWith("2 items could not be synced"))
    }

    @Test
    fun decisionOnlyCountsCurrentUsersItems_viaManager() {
        val m = OfflineQueueManager(InMemorySharedPreferences())
        m.enqueueAction(a("CHECK_IN", "1").copy(userId = "userA"))
        assertEquals(LogoutDecision.Proceed, LogoutPolicy.decide(m.getQueueForUser("userB")))
        assertTrue(LogoutPolicy.decide(m.getQueueForUser("userA")) is LogoutDecision.ConfirmUnsynced)
    }

    @Test
    fun deletionWarningMentionsLoss() {
        assertTrue(LogoutPolicy.DELETION_WARNING.contains("lost"))
    }
}
