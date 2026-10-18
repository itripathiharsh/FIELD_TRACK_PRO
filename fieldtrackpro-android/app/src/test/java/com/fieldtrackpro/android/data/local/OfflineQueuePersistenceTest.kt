package com.fieldtrackpro.android.data.local

import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Offline queue persistence + scheduling-after-enqueue + backwards compatibility of persisted JSON.
 * The persisted JSON field names must never change (they are written by older app versions).
 */
class OfflineQueuePersistenceTest {

    // JSON exactly as persisted by pre-@SerializedName builds (Gson used the Kotlin property names).
    private val legacyQueueJson = """
        [{"id":"a-1","userId":"user-9","visitId":"visit-1","actionType":"CHECK_IN",
          "latitude":19.0760,"longitude":72.8777,"timestamp":1700000000000,
          "notes":"left a note","accuracyM":12.5,"isMockLocation":true},
         {"id":"a-2","visitId":"visit-2","actionType":"CHECK_OUT","latitude":1.5,"longitude":2.5}]
    """.trimIndent()

    private val legacyConflictJson = """
        [{"id":"c-1","pendingAction":{"id":"a-1","userId":"user-9","visitId":"visit-1","actionType":"CHECK_IN",
          "latitude":19.0,"longitude":72.0,"timestamp":1700000000000,"isMockLocation":false},
          "conflictType":"STATUS_CHANGED","serverStatus":"COMPLETED","message":"already done","detectedAt":1700000001000}]
    """.trimIndent()

    @Test
    fun legacyPendingActionJson_stillParses() {
        val type = object : TypeToken<List<PendingAction>>() {}.type
        val list: List<PendingAction> = Gson().fromJson(legacyQueueJson, type)
        assertEquals(2, list.size)
        val first = list[0]
        assertEquals("a-1", first.id)
        assertEquals("user-9", first.userId)
        assertEquals("visit-1", first.visitId)
        assertEquals("CHECK_IN", first.actionType)
        assertEquals(19.0760, first.latitude, 0.0)
        assertEquals(72.8777, first.longitude, 0.0)
        assertEquals(1700000000000L, first.timestamp)
        assertEquals("left a note", first.notes)
        assertEquals(12.5, first.accuracyM!!, 0.0)
        assertTrue(first.isMockLocation)
        // Older record without optional fields
        assertNull(list[1].userId)
        assertNull(list[1].notes)
        assertFalse(list[1].isMockLocation)
    }

    @Test
    fun legacySyncConflictJson_stillParses() {
        val type = object : TypeToken<List<SyncConflict>>() {}.type
        val list: List<SyncConflict> = Gson().fromJson(legacyConflictJson, type)
        assertEquals(1, list.size)
        assertEquals("c-1", list[0].id)
        assertEquals(ConflictType.STATUS_CHANGED, list[0].conflictType)
        assertEquals("COMPLETED", list[0].serverStatus)
        assertEquals("a-1", list[0].pendingAction.id)
        assertEquals(1700000001000L, list[0].detectedAt)
    }

    @Test
    fun serializedJsonKeepsExactLegacyFieldNames() {
        val json = Gson().toJson(
            PendingAction(
                id = "x", userId = "u", visitId = "v", actionType = "CHECK_IN",
                latitude = 1.0, longitude = 2.0, timestamp = 3L, notes = "n", accuracyM = 4.0, isMockLocation = true
            )
        )
        for (name in listOf("id", "userId", "visitId", "actionType", "latitude", "longitude", "timestamp", "notes", "accuracyM", "isMockLocation")) {
            assertTrue("missing field $name in $json", json.contains("\"$name\":"))
        }
    }

    @Test
    fun managerReadsLegacyQueueFromPreferences() {
        val prefs = InMemorySharedPreferences()
        prefs.edit().putString("pending_queue", legacyQueueJson).putString("sync_conflicts", legacyConflictJson).apply()
        val manager = OfflineQueueManager(prefs, previousUserIdProvider = { "user-9" })
        assertEquals(2, manager.getQueue().size)
        assertEquals(1, manager.getConflicts().size)
        assertEquals(listOf("a-1", "a-2"), manager.getQueueForUser("user-9").map { it.id })
    }

    @Test
    fun enqueueAction_schedulesSyncAfterEveryEnqueue() {
        var scheduled = 0
        val manager = OfflineQueueManager(InMemorySharedPreferences()) { scheduled++ }

        manager.enqueueAction(PendingAction(visitId = "v1", actionType = "CHECK_IN", latitude = 1.0, longitude = 2.0))
        manager.enqueueAction(PendingAction(visitId = "v1", actionType = "CHECK_OUT", latitude = 1.0, longitude = 2.0))
        manager.enqueueAction(PendingAction(visitId = "workday", actionType = "START_DAY", latitude = 1.0, longitude = 2.0))

        assertEquals(3, scheduled)
        assertEquals(3, manager.getQueue().size)
    }

    @Test
    fun enqueueAction_survivesSchedulerFailure() {
        val manager = OfflineQueueManager(InMemorySharedPreferences()) { throw IllegalStateException("WorkManager unavailable") }
        manager.enqueueAction(PendingAction(visitId = "v1", actionType = "CHECK_IN", latitude = 1.0, longitude = 2.0))
        assertEquals("Action must be persisted even if scheduling fails", 1, manager.getQueue().size)
    }

    @Test
    fun enqueueAction_replacesDuplicateVisitAndTypeAndStillSchedules() {
        var scheduled = 0
        val manager = OfflineQueueManager(InMemorySharedPreferences()) { scheduled++ }
        manager.enqueueAction(PendingAction(id = "1", visitId = "v1", actionType = "CHECK_IN", latitude = 1.0, longitude = 2.0))
        manager.enqueueAction(PendingAction(id = "2", visitId = "v1", actionType = "CHECK_IN", latitude = 5.0, longitude = 6.0))
        assertEquals(1, manager.getQueue().size)
        assertEquals("2", manager.getQueue()[0].id)
        assertEquals(2, scheduled)
    }
}
