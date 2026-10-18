package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.CustomerApi
import com.fieldtrackpro.android.data.api.GeoApi
import com.fieldtrackpro.android.data.api.VisitApi
import com.fieldtrackpro.android.data.local.AccountDataWiper
import com.fieldtrackpro.android.data.local.ConflictType
import com.fieldtrackpro.android.data.local.InMemorySharedPreferences
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.OutletProofPayload
import com.fieldtrackpro.android.data.local.PaymentQueuePayload
import com.fieldtrackpro.android.data.local.PendingAction
import com.fieldtrackpro.android.data.local.SyncConflict
import com.fieldtrackpro.android.data.local.TokenManager
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.lang.reflect.Proxy

class SyncHardeningTest {

    private val user = "u1"

    private fun payAction(key: String, proofs: List<String>) = PendingAction(
        userId = user, visitId = "v1", actionType = PendingAction.TYPE_PAYMENT_CREATE, latitude = 0.0, longitude = 0.0,
        paymentPayload = PaymentQueuePayload(
            idempotencyKey = key, customerId = "c1", outletName = "S", amount = "10", paymentMethod = "CASH",
            paymentDate = "2026-10-10", proofPaths = proofs
        )
    )

    // ------------------------------------------------------------------ too-large proof is kept, not deleted

    @Test
    fun tooLargeDetection() {
        assertTrue(PaymentQueueProcessor.isTooLargeRejection(413, null))
        assertTrue(PaymentQueueProcessor.isTooLargeRejection(422, """{"error":{"code":"FILE_TOO_LARGE","message":"Image exceeds 10 MB"}}"""))
        assertFalse(PaymentQueueProcessor.isTooLargeRejection(422, """{"error":{"code":"VALIDATION","message":"bad amount"}}"""))
        assertFalse(PaymentQueueProcessor.isTooLargeRejection(400, null))
        assertFalse(PaymentQueueProcessor.isTooLargeRejection(500, null))
    }

    @Test
    fun proofRejectedAsTooLarge413_keepsTheFile_andTheConflictStillPointsToIt() = runBlocking {
        val api = FakeCollectionApi()
        api.proofBehavior = { api.proofErr(413, """{"error":{"message":"Payload too large"}}""") }
        val queue = OfflineQueueManager(InMemorySharedPreferences())
        val deleted = mutableListOf<String>()
        val files = mapOf("/p/big.jpg" to byteArrayOf(1, 2, 3))
        val processor = PaymentQueueProcessor(api, queue, { files[it] }, { deleted += it })
        val action = payAction("k", listOf("/p/big.jpg"))
        queue.enqueueAction(action)

        val out = processor.replay(action)

        assertTrue(out is PaymentReplayOutcome.Conflict)
        val conflict = (out as PaymentReplayOutcome.Conflict).conflict
        assertTrue("file must NOT be deleted until the user retakes/discards", deleted.isEmpty())
        assertEquals(listOf("/p/big.jpg"), conflict.pendingAction.paymentPayload?.proofPaths)
        assertTrue(queue.getQueue().isEmpty())
    }

    @Test
    fun proofRejectedAsOtherPermanentError_isStillDeleted_andOtherProofsStillUpload() = runBlocking {
        val api = FakeCollectionApi()
        var n = 0
        api.proofBehavior = { if (n++ == 0) api.proofErr(415, """{"error":{"message":"Unsupported type"}}""") else null }
        val queue = OfflineQueueManager(InMemorySharedPreferences())
        val deleted = mutableListOf<String>()
        val files = mapOf("/p/a.jpg" to byteArrayOf(1), "/p/b.jpg" to byteArrayOf(2))
        val processor = PaymentQueueProcessor(api, queue, { files[it] }, { deleted += it })
        val action = payAction("k2", listOf("/p/a.jpg", "/p/b.jpg"))
        queue.enqueueAction(action)

        val out = processor.replay(action)

        assertTrue(out is PaymentReplayOutcome.Conflict)
        assertEquals(setOf("/p/a.jpg", "/p/b.jpg"), deleted.toSet())
        assertEquals(2, api.proofUploadCalls)
    }

    @Test
    fun forcedPasswordChange403_duringReplay_pausesInsteadOfConflict() = runBlocking {
        val api = FakeCollectionApi()
        api.createBehavior = { api.err(403, """{"error":{"code":"PASSWORD_CHANGE_REQUIRED","message":"Change password"}}""") }
        val queue = OfflineQueueManager(InMemorySharedPreferences())
        val action = payAction("k3", emptyList())
        queue.enqueueAction(action)

        val out = PaymentQueueProcessor(api, queue).replay(action)

        assertEquals(PaymentReplayOutcome.AuthExpired, out) // "pause" outcome: queue untouched
        assertEquals(1, queue.getQueue().size)
    }

    @Test
    fun ordinary403_isStillAConflict() = runBlocking {
        val api = FakeCollectionApi()
        api.createBehavior = { api.err(403, """{"error":{"code":"FORBIDDEN","message":"Not yours"}}""") }
        val queue = OfflineQueueManager(InMemorySharedPreferences())
        val action = payAction("k4", emptyList())
        queue.enqueueAction(action)
        assertTrue(PaymentQueueProcessor(api, queue).replay(action) is PaymentReplayOutcome.Conflict)
    }

    // ------------------------------------------------------------------ VisitRepository sync: pause + user switch

    private inline fun <reified T> stub(crossinline handler: (String) -> Any?): T =
        Proxy.newProxyInstance(T::class.java.classLoader, arrayOf(T::class.java)) { _, m, args ->
            when (m.name) {
                "toString" -> "stub"
                "hashCode" -> 1
                "equals" -> false
                else -> handler(m.name + ":" + (args?.firstOrNull() ?: ""))
            }
        } as T

    private fun repo(api: FakeCollectionApi, queue: OfflineQueueManager, tokens: TokenManager?) = VisitRepository(
        visitApi = stub<VisitApi> { throw IllegalStateException("unexpected $it") },
        customerApi = stub<CustomerApi> { null },
        geoApi = stub<GeoApi> { null },
        offlineQueueManager = queue,
        tokenManager = tokens,
        collectionApi = api
    )

    private fun session(userId: String, mustChange: Boolean = false) = TokenManager(null, InMemorySharedPreferences()).apply {
        saveTokens("a", "r")
        saveUserProfile("N", null, "EMPLOYEE", id = userId)
        setPasswordChangeRequired(mustChange)
    }

    @Test
    fun syncPausesWithoutFailingOrConflicting_whilePasswordChangeIsPending() = runBlocking {
        val api = FakeCollectionApi()
        val queue = OfflineQueueManager(InMemorySharedPreferences())
        queue.enqueueAction(payAction("k5", emptyList()))

        val result = repo(api, queue, session(user, mustChange = true)).syncOfflineQueue(activeUserId = user)

        assertTrue(result.pausedForPasswordChange)
        assertTrue(result.pausedForAuth)
        assertTrue(result.conflicts.isEmpty())
        assertEquals("no network call while pending", 0, api.createCalls.size)
        assertEquals("entry stays queued", 1, queue.getQueueForUser(user).size)
        assertTrue(queue.getConflictsForUser(user).isEmpty())
    }

    @Test
    fun syncResumesNormallyAfterThePasswordIsChanged() = runBlocking {
        val api = FakeCollectionApi()
        val queue = OfflineQueueManager(InMemorySharedPreferences())
        queue.enqueueAction(payAction("k6", emptyList()))
        val tokens = session(user, mustChange = true)
        val repository = repo(api, queue, tokens)

        assertTrue(repository.syncOfflineQueue(activeUserId = user).pausedForPasswordChange)
        tokens.setPasswordChangeRequired(false)
        val result = repository.syncOfflineQueue(activeUserId = user)

        assertEquals(1, result.syncedCount)
        assertTrue(queue.getQueueForUser(user).isEmpty())
    }

    @Test
    fun syncStopsReplaying_whenTheActiveUserChangesMidRun() = runBlocking {
        val api = FakeCollectionApi()
        val queue = OfflineQueueManager(InMemorySharedPreferences())
        queue.enqueueAction(payAction("k7", emptyList()))
        queue.enqueueAction(payAction("k8", emptyList()))
        val tokens = session(user)
        // the first payment's create call "logs out and switches user" as a side effect (mid-run change)
        api.createBehavior = {
            tokens.clear()
            tokens.saveTokens("a2", "r2")
            tokens.saveUserProfile("Other", null, "EMPLOYEE", id = "u2")
            null
        }

        val result = repo(api, queue, tokens).syncOfflineQueue(activeUserId = user)

        assertEquals("second action must never be sent under the new user", 1, api.createCalls.size)
        assertFalse(result.pausedForAuth)
        assertEquals(1, queue.getQueue().count { it.userId == user })
    }

    @Test
    fun syncStopsWhenSessionIsClearedMidRun() = runBlocking {
        val api = FakeCollectionApi()
        val queue = OfflineQueueManager(InMemorySharedPreferences())
        queue.enqueueAction(payAction("k9", emptyList()))
        queue.enqueueAction(payAction("k10", emptyList()))
        val tokens = session(user)
        api.createBehavior = { tokens.clear(); null }
        repo(api, queue, tokens).syncOfflineQueue(activeUserId = user)
        assertEquals(1, api.createCalls.size)
    }

    // ------------------------------------------------------------------ account-deletion wipe

    @Test
    fun wipe_removesAllOfTheUsersLocalData_butNotAnotherUsers() {
        val queue = OfflineQueueManager(InMemorySharedPreferences())
        queue.enqueueAction(payAction("w1", listOf("/pay/1.jpg", "/pay/2.jpg")))
        queue.enqueueAction(
            PendingAction(
                userId = user, visitId = "o", actionType = PendingAction.TYPE_OUTLET_PROOF, latitude = 0.0, longitude = 0.0,
                outletProofPayload = OutletProofPayload(idempotencyKey = "ok", photoPath = "/out/1.jpg")
            )
        )
        queue.addConflict(
            SyncConflict(
                pendingAction = payAction("w2", listOf("/pay/kept.jpg")), conflictType = ConflictType.SERVER_REJECTED,
                serverStatus = "413", message = "too large"
            )
        )
        val otherUser = payAction("w3", listOf("/pay/other.jpg")).copy(userId = "u2")
        queue.enqueueAction(otherUser)
        val deleted = mutableListOf<String>()
        var draftsClearedFor: String? = null
        var extra = 0

        val n = AccountDataWiper(queue, { deleted += it }, { draftsClearedFor = it }, { extra++ }).wipe(user)

        assertEquals(4, n)
        assertEquals(setOf("/pay/1.jpg", "/pay/2.jpg", "/out/1.jpg", "/pay/kept.jpg"), deleted.toSet())
        assertEquals(user, draftsClearedFor)
        assertEquals(1, extra)
        assertTrue(queue.getQueueForUser(user).isEmpty())
        assertTrue(queue.getConflictsForUser(user).isEmpty())
        assertEquals(1, queue.getQueue().size)
        assertEquals("u2", queue.getQueue().single().userId)
        assertNull(deleted.firstOrNull { it.contains("other") })
    }

    @Test
    fun wipe_withNoKnownUser_stillRunsExtraCleanup() {
        var extra = 0
        val n = AccountDataWiper(OfflineQueueManager(InMemorySharedPreferences()), {}, {}, { extra++ }).wipe(null)
        assertEquals(0, n)
        assertEquals(1, extra)
    }
}
