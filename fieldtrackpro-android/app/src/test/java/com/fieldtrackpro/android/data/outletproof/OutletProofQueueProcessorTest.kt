package com.fieldtrackpro.android.data.outletproof

import com.fieldtrackpro.android.data.api.CustomerApi
import com.fieldtrackpro.android.data.api.GeoApi
import com.fieldtrackpro.android.data.api.VisitApi
import com.fieldtrackpro.android.data.local.ConflictType
import com.fieldtrackpro.android.data.local.InMemorySharedPreferences
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.OutletProofPayload
import com.fieldtrackpro.android.data.local.PendingAction
import com.fieldtrackpro.android.data.repository.OUTLET_PROOF_STALE_STATUS
import com.fieldtrackpro.android.data.repository.OutletProofMessages
import com.fieldtrackpro.android.data.repository.OutletProofQueueProcessor
import com.fieldtrackpro.android.data.repository.OutletProofReplayOutcome
import com.fieldtrackpro.android.data.repository.VisitRepository
import com.fieldtrackpro.android.data.repository.isStaleOutletProof
import com.fieldtrackpro.android.data.repository.needsOutletRetake
import kotlinx.coroutines.runBlocking
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.Response
import java.io.IOException
import java.lang.reflect.Proxy

class OutletProofQueueProcessorTest {
    private val user = "u1"

    private fun action(key: String = "key-12345678", customer: String = "c1", path: String = "/p/1.jpg", userId: String = user) = PendingAction(
        userId = userId, visitId = customer, actionType = PendingAction.TYPE_OUTLET_PROOF, latitude = 28.0, longitude = 77.0,
        outletProofPayload = OutletProofPayload(
            idempotencyKey = key, customerId = customer, outletName = "Sharma Store", photoPath = path,
            latitude = 28.0, longitude = 77.0, accuracyM = 10.0, capturedAt = "2026-10-13T16:25:01.123+05:30",
            capturedAtEpochMs = 5L, deviceInfo = "Pixel"
        )
    )

    private class Env(files: Map<String, ByteArray> = mapOf("/p/1.jpg" to byteArrayOf(1, 2, 3), "/p/2.jpg" to byteArrayOf(4))) {
        val api = FakeOutletProofApi()
        val queue = OfflineQueueManager(InMemorySharedPreferences())
        val deleted = mutableListOf<String>()
        val processor = OutletProofQueueProcessor(api, queue, { files[it] }, { deleted += it })
    }

    @Test
    fun success_removesFromQueue_deletesPhoto_usesSameKey() = runBlocking {
        val e = Env()
        val a = action()
        e.queue.enqueueAction(a)
        val out = e.processor.replay(a)
        assertTrue(out is OutletProofReplayOutcome.Synced)
        assertTrue(e.queue.getQueue().isEmpty())
        assertEquals(listOf("/p/1.jpg"), e.deleted)
        assertEquals("key-12345678", e.api.uploads.single().fields["idempotency_key"])
        assertEquals("c1", e.api.uploads.single().fields["customer_id"])
    }

    @Test
    fun networkFailureThenRetry_reusesKey_onlyOneServerProof() = runBlocking {
        val e = Env()
        val a = action()
        e.queue.enqueueAction(a)
        e.api.throwsOnUpload = IOException("no network")
        assertEquals(OutletProofReplayOutcome.Retry, e.processor.replay(a))
        assertEquals(1, e.queue.getQueue().size)
        assertTrue(e.deleted.isEmpty())
        e.api.throwsOnUpload = null
        assertTrue(e.processor.replay(e.queue.getQueue().single()) is OutletProofReplayOutcome.Synced)
        assertEquals(1, e.api.stored.size)
        assertEquals(setOf("key-12345678"), e.api.uploads.map { it.fields["idempotency_key"] }.toSet())
    }

    @Test
    fun transient_5xx_408_429_retry() = runBlocking {
        for (code in listOf(500, 502, 408, 429)) {
            val e = Env()
            val a = action()
            e.queue.enqueueAction(a)
            e.api.behavior = { e.api.err(code) }
            assertEquals("code $code", OutletProofReplayOutcome.Retry, e.processor.replay(a))
            assertEquals(1, e.queue.getQueue().size)
        }
    }

    @Test
    fun unauthorized401_pausesAndKeepsQueue() = runBlocking {
        val e = Env()
        val a = action()
        e.queue.enqueueAction(a)
        e.api.behavior = { e.api.err(401) }
        assertEquals(OutletProofReplayOutcome.AuthExpired, e.processor.replay(a))
        assertEquals(1, e.queue.getQueue().size)
        assertTrue(e.deleted.isEmpty())
    }

    @Test
    fun notFound404_isConflictWithFriendlyMessage() = runBlocking {
        val e = Env()
        val a = action()
        e.api.behavior = { e.api.err(404) }
        val out = e.processor.replay(a) as OutletProofReplayOutcome.Conflict
        assertEquals(ConflictType.VISIT_UNAVAILABLE, out.conflict.conflictType)
        assertTrue(out.conflict.message.contains("no longer available"))
    }

    @Test
    fun stale422_becomesVisibleConflict_withRetakeMessage_andRetakeAction() = runBlocking {
        val e = Env()
        val a = action()
        e.queue.enqueueAction(a)
        e.api.behavior = { e.api.errCode(422, "OUTLET_PROOF_STALE_CAPTURE", "captured_at too old") }

        val out = e.processor.replay(a) as OutletProofReplayOutcome.Conflict
        assertEquals("Photo was taken too long ago to verify. Please retake it at the outlet.", out.conflict.message)
        assertEquals(OUTLET_PROOF_STALE_STATUS, out.conflict.serverStatus)
        assertTrue(out.conflict.isStaleOutletProof)
        assertTrue(out.conflict.needsOutletRetake)
        assertEquals(listOf("/p/1.jpg"), e.deleted)

        e.queue.moveToConflict(out.conflict)
        assertTrue("never retried forever", e.queue.getQueue().isEmpty())
        val shown = e.queue.getConflictsForUser(user).single()
        assertTrue(shown.isStaleOutletProof)
    }

    @Test
    fun otherRejections_keepServerMessage_noRetakeForAlreadyPending() = runBlocking {
        val e = Env()
        val a = action()
        e.api.behavior = { e.api.errCode(409, "OUTLET_PROOF_ALREADY_PENDING") }
        val out = e.processor.replay(a) as OutletProofReplayOutcome.Conflict
        assertTrue(out.conflict.message.contains("waiting for admin review"))
        assertFalse(out.conflict.isStaleOutletProof)
        assertFalse(out.conflict.needsOutletRetake)
    }

    @Test
    fun missingPhotoFile_isConflictNotInfiniteRetry() = runBlocking {
        val e = Env(emptyMap())
        val out = e.processor.replay(action()) as OutletProofReplayOutcome.Conflict
        assertTrue(out.conflict.needsOutletRetake)
        assertEquals(OutletProofMessages.PHOTO_MISSING, out.conflict.message)
        assertTrue(e.api.uploads.isEmpty())
    }

    @Test
    fun missingPayload_isConflict() = runBlocking {
        val e = Env()
        val broken = PendingAction(userId = user, visitId = "c1", actionType = PendingAction.TYPE_OUTLET_PROOF, latitude = 0.0, longitude = 0.0)
        assertTrue(e.processor.replay(broken) is OutletProofReplayOutcome.Conflict)
    }

    // ------------------------------------------------------------------ queue storage / back-compat

    @Test
    fun enqueueDedup_sameKeyReplaced_differentKeyKept_perUser() {
        val q = OfflineQueueManager(InMemorySharedPreferences())
        q.enqueueAction(action(key = "KEY-AAAAAAAA"))
        q.enqueueAction(action(key = "KEY-AAAAAAAA"))
        assertEquals(1, q.getQueue().size)
        q.enqueueAction(action(key = "KEY-BBBBBBBB"))
        assertEquals(2, q.getQueue().size)
        q.enqueueAction(action(key = "KEY-AAAAAAAA", userId = "other"))
        assertEquals("another user's identical key is a separate entry", 3, q.getQueue().size)
        assertEquals(2, q.getQueueForUser(user).size)
    }

    @Test
    fun jsonRoundTrip_usesSerializedNames_andOldEntriesStillParse() {
        val prefs = InMemorySharedPreferences()
        OfflineQueueManager(prefs).enqueueAction(action(key = "KEY-RT-123456"))
        val reread = OfflineQueueManager(prefs).getQueueForUser(user).single()
        assertEquals("KEY-RT-123456", reread.outletProofPayload?.idempotencyKey)
        assertTrue(reread.isOutletProof)
        val json = prefs.getString("pending_queue", "")!!
        assertTrue(json.contains("\"outletProofPayload\""))
        assertTrue(json.contains("\"photoPath\":\"/p/1.jpg\""))
        assertTrue(json.contains("\"idempotencyKey\":\"KEY-RT-123456\""))

        val old = InMemorySharedPreferences()
        old.edit().putString(
            "pending_queue",
            """[{"id":"x","userId":"u1","visitId":"v","actionType":"CHECK_IN","latitude":1.0,"longitude":2.0,"timestamp":5},
               {"id":"y","userId":"u1","visitId":"v","actionType":"PAYMENT_CREATE","latitude":0.0,"longitude":0.0,"paymentPayload":{"idempotencyKey":"p"}}]"""
        ).apply()
        val items = OfflineQueueManager(old).getQueueForUser("u1")
        assertEquals(2, items.size)
        assertTrue(items.all { it.outletProofPayload == null && !it.isOutletProof })
    }

    // ------------------------------------------------------------------ sync ordering (VisitRepository)

    private inline fun <reified T> stub(crossinline handler: (String) -> Any?): T =
        Proxy.newProxyInstance(T::class.java.classLoader, arrayOf(T::class.java)) { _, m, args ->
            when (m.name) {
                "toString" -> "stub"
                "hashCode" -> 1
                "equals" -> false
                else -> handler(m.name + ":" + (args?.firstOrNull() ?: ""))
            }
        } as T

    @Test
    fun sync_replaysOutletPhotosFirst_andMovesStaleToConflict() = runBlocking {
        val api = FakeOutletProofApi()
        val log = mutableListOf<String>()
        val queue = OfflineQueueManager(InMemorySharedPreferences())
        api.behavior = {
            log += "proof:" + (api.uploads.last().fields["idempotency_key"] ?: "?")
            if (api.uploads.size == 2) api.errCode(422, "OUTLET_PROOF_STALE_CAPTURE") else null
        }
        val visitApi = stub<VisitApi> { call ->
            log += call
            Response.error<Any>(500, "{}".toResponseBody("application/json".toMediaTypeOrNull()))
        }
        // The default file reader can't see /p/*.jpg: write real temp files.
        val dir = java.nio.file.Files.createTempDirectory("proofs").toFile()
        try {
            val f1 = java.io.File(dir, "1.jpg").also { it.writeBytes(byteArrayOf(1)) }
            val f2 = java.io.File(dir, "2.jpg").also { it.writeBytes(byteArrayOf(2)) }
            queue.enqueueAction(PendingAction(userId = user, visitId = "v1", actionType = "CHECK_OUT", latitude = 1.0, longitude = 2.0))
            queue.enqueueAction(action(key = "KEY-ORDER-0001", path = f1.absolutePath))
            queue.enqueueAction(action(key = "KEY-ORDER-0002", customer = "c2", path = f2.absolutePath))
            val repo = VisitRepository(
                visitApi = visitApi, customerApi = stub<CustomerApi> { null }, geoApi = stub<GeoApi> { null },
                offlineQueueManager = queue, outletProofApi = api
            )

            val result = repo.syncOfflineQueue(activeUserId = user)

            assertEquals("proofs run in capture order before visit actions: $log", "proof:KEY-ORDER-0001", log[0])
            assertEquals("proof:KEY-ORDER-0002", log[1])
            assertTrue(log.drop(2).all { it.startsWith("getVisitById") || it.startsWith("checkOut") })
            assertTrue("the first proof synced: ${result.syncedCount}", result.syncedCount >= 1)
            assertEquals(1, result.conflicts.count { it.pendingAction.isOutletProof })
            assertTrue(queue.getConflictsForUser(user).single { it.pendingAction.isOutletProof }.isStaleOutletProof)
            assertTrue(queue.getQueueForUser(user).none { it.isOutletProof })
        } finally {
            dir.deleteRecursively()
        }
    }
}
