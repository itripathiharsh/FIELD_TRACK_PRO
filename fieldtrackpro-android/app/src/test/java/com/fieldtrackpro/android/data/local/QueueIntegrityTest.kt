package com.fieldtrackpro.android.data.local

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

/** Durability, cross-instance atomicity and corruption handling of [OfflineQueueManager]. */
class QueueIntegrityTest {

    /** Records which write mode every edit used, delegating to a real in-memory store. */
    private class RecordingPrefs(private val d: InMemorySharedPreferences = InMemorySharedPreferences()) :
        android.content.SharedPreferences by d {
        val applies = AtomicInteger()
        val commits = AtomicInteger()
        override fun edit(): android.content.SharedPreferences.Editor {
            val inner = d.edit()
            return object : android.content.SharedPreferences.Editor by inner {
                override fun putString(key: String?, value: String?) = apply { inner.putString(key, value) }
                override fun remove(key: String?) = apply { inner.remove(key) }
                override fun clear() = apply { inner.clear() }
                override fun putBoolean(key: String?, value: Boolean) = apply { inner.putBoolean(key, value) }
                override fun apply() { applies.incrementAndGet(); inner.apply() }
                override fun commit(): Boolean { commits.incrementAndGet(); return inner.commit() }
            }
        }
    }

    private fun action(id: String, user: String = "u1", type: String = "CHECK_IN") =
        PendingAction(id = id, userId = user, visitId = "v-$id", actionType = type, latitude = 1.0, longitude = 2.0)

    // ------------------------------------------------------------------ durability

    @Test
    fun queueAndConflictWrites_useCommitNeverApply() {
        val prefs = RecordingPrefs()
        val q = OfflineQueueManager(prefs)
        q.enqueueAction(action("a"))
        q.updateAction(action("a").copy(notes = "n"))
        q.addConflict(SyncConflict(pendingAction = action("c"), conflictType = ConflictType.SERVER_REJECTED, serverStatus = null, message = "m"))
        val id = q.getConflicts().single().id
        q.removeConflict(id)
        q.clearConflicts()
        q.moveToConflict(SyncConflict(pendingAction = action("a"), conflictType = ConflictType.SERVER_REJECTED, serverStatus = null, message = "m"))
        q.removeAction("a")
        assertEquals("a process kill must never lose an acknowledged write", 0, prefs.applies.get())
        assertTrue(prefs.commits.get() >= 6)
    }

    @Test
    fun tokenSave_usesCommit() {
        val prefs = RecordingPrefs()
        val tm = TokenManager(null, prefs)
        tm.saveTokens("a", "r")
        tm.setPasswordChangeRequired(true)
        assertEquals(0, prefs.applies.get())
        assertEquals("r", tm.getRefreshToken())
    }

    // ------------------------------------------------------------------ process-wide lock

    @Test
    fun manyInstancesOverTheSameStore_concurrentEnqueues_loseNothing() {
        val shared = InMemorySharedPreferences()
        val threads = 8
        val perThread = 25
        val pool = Executors.newFixedThreadPool(threads)
        val start = CountDownLatch(1)
        val done = CountDownLatch(threads)
        for (t in 0 until threads) {
            pool.submit {
                // each thread has its OWN manager instance (like MainActivity / WorkdayViewModel / worker)
                val q = OfflineQueueManager(shared)
                start.await()
                for (i in 0 until perThread) q.enqueueAction(action("t$t-$i", type = "CHECK_IN"))
                done.countDown()
            }
        }
        start.countDown()
        assertTrue(done.await(30, TimeUnit.SECONDS))
        pool.shutdown()
        val all = OfflineQueueManager(shared).getQueue()
        assertEquals(threads * perThread, all.size)
        assertEquals(threads * perThread, all.map { it.id }.toSet().size)
    }

    @Test
    fun workerRemovals_racingNewEnqueues_neverResurrectOrDropEntries() {
        val shared = InMemorySharedPreferences()
        val seed = OfflineQueueManager(shared)
        for (i in 0 until 50) seed.enqueueAction(action("old-$i"))
        val pool = Executors.newFixedThreadPool(2)
        val done = CountDownLatch(2)
        pool.submit { // "sync worker" instance: removes + updates synced entries
            val q = OfflineQueueManager(shared)
            for (i in 0 until 50) { q.updateAction(action("old-$i").copy(notes = "p")); q.removeAction("old-$i") }
            done.countDown()
        }
        pool.submit { // UI instance: enqueues new work meanwhile
            val q = OfflineQueueManager(shared)
            for (i in 0 until 50) q.enqueueAction(action("new-$i"))
            done.countDown()
        }
        assertTrue(done.await(30, TimeUnit.SECONDS))
        pool.shutdown()
        val ids = OfflineQueueManager(shared).getQueue().map { it.id }.toSet()
        assertEquals((0 until 50).map { "new-$it" }.toSet(), ids)
    }

    @Test
    fun getInstance_isNotUsedByTests_butCompanionLockIsProcessWide() {
        // two managers over one store see each other's writes immediately
        val shared = InMemorySharedPreferences()
        val a = OfflineQueueManager(shared)
        val b = OfflineQueueManager(shared)
        a.enqueueAction(action("1"))
        b.enqueueAction(action("2"))
        assertEquals(setOf("1", "2"), a.getQueue().map { it.id }.toSet())
    }

    // ------------------------------------------------------------------ corruption

    @Test
    fun corruptedQueueBlob_isQuarantined_notSilentlyDropped_andAppendsStaySafe() {
        val prefs = InMemorySharedPreferences()
        val garbage = """[{"id":"x","visitId":"v" BROKEN"""
        prefs.edit().putString("pending_queue", garbage).commit()
        val q = OfflineQueueManager(prefs)

        assertTrue(q.getQueue().isEmpty())

        // raw blob preserved under a quarantine key
        val backupKeys = q.getCorruptionBackupKeys()
        assertEquals(1, backupKeys.size)
        assertEquals(garbage, prefs.getString(backupKeys.single(), null))
        // user/support is told
        val notice = q.getConflicts().single()
        assertEquals(ConflictType.QUEUE_CORRUPTED, notice.conflictType)
        assertEquals(backupKeys.single(), notice.serverStatus)

        // new entries append normally and do not overwrite the evidence
        q.enqueueAction(action("fresh"))
        q.enqueueAction(action("fresh2"))
        assertEquals(listOf("fresh", "fresh2"), q.getQueue().map { it.id })
        assertEquals(garbage, prefs.getString(backupKeys.single(), null))
        // parsing again does not quarantine a second time
        assertEquals(1, q.getCorruptionBackupKeys().size)
        assertEquals(1, q.getConflicts().size)
    }

    @Test
    fun corruptedConflictBlob_isQuarantined_andQueueUntouched() {
        val prefs = InMemorySharedPreferences()
        val q = OfflineQueueManager(prefs)
        q.enqueueAction(action("keep"))
        prefs.edit().putString("sync_conflicts", "{{not json").commit()

        val conflicts = q.getConflicts()

        assertEquals(1, conflicts.size)
        assertEquals(ConflictType.QUEUE_CORRUPTED, conflicts.single().conflictType)
        assertEquals(listOf("keep"), q.getQueue().map { it.id })
        assertEquals(1, q.getCorruptionBackupKeys().size)
    }

    @Test
    fun healthyEmptyAndMissingBlobs_areNotTreatedAsCorruption() {
        val q = OfflineQueueManager(InMemorySharedPreferences())
        assertTrue(q.getQueue().isEmpty())
        assertTrue(q.getConflicts().isEmpty())
        assertTrue(q.getCorruptionBackupKeys().isEmpty())
    }

    // ------------------------------------------------------------------ purge for account deletion

    @Test
    fun purgeUser_removesOnlyThatUsersEntriesAndConflicts_andReturnsTheirFiles() {
        val q = OfflineQueueManager(InMemorySharedPreferences())
        val pay = action("p1", "u1", PendingAction.TYPE_PAYMENT_CREATE).copy(
            paymentPayload = PaymentQueuePayload(
                idempotencyKey = "k", customerId = "c", outletName = null, amount = "1", paymentMethod = "CASH",
                paymentDate = "2026-01-01", proofPaths = listOf("/p/1.jpg")
            )
        )
        q.enqueueAction(pay)
        q.enqueueAction(action("a1", "u1"))
        q.enqueueAction(action("b1", "u2"))
        q.addConflict(SyncConflict(pendingAction = action("c1", "u1"), conflictType = ConflictType.SERVER_REJECTED, serverStatus = null, message = "m"))
        q.addConflict(SyncConflict(pendingAction = action("c2", "u2"), conflictType = ConflictType.SERVER_REJECTED, serverStatus = null, message = "m"))

        val files = q.purgeUser("u1")

        assertEquals(listOf("/p/1.jpg"), files)
        assertEquals(listOf("b1"), q.getQueue().map { it.id })
        assertEquals(listOf("c2"), q.getConflicts().map { it.pendingAction.id })
        assertFalse(q.getQueue().any { it.userId == "u1" })
    }
}
