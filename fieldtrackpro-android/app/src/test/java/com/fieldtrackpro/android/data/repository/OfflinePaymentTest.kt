package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.CustomerApi
import com.fieldtrackpro.android.data.api.GeoApi
import com.fieldtrackpro.android.data.api.VisitApi
import com.fieldtrackpro.android.data.local.ConflictType
import com.fieldtrackpro.android.data.local.InMemorySharedPreferences
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.PaymentQueuePayload
import com.fieldtrackpro.android.data.local.PendingAction
import com.fieldtrackpro.android.data.local.SyncErrorPolicy
import com.fieldtrackpro.android.data.model.BrandAllocationInput
import kotlinx.coroutines.runBlocking
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.Response
import java.io.IOException
import java.lang.reflect.Proxy

class OfflinePaymentTest {

    private val user = "u1"

    private fun payload(key: String = "key-1", proofs: List<String> = emptyList()) = PaymentQueuePayload(
        idempotencyKey = key, customerId = "c1", outletName = "Sharma Store", amount = "2500.0",
        paymentMethod = "CASH", paymentDate = "2026-10-10", notes = "n",
        allocations = listOf(BrandAllocationInput("BrandA", 2500.0)), proofPaths = proofs
    )

    private fun payAction(key: String = "key-1", visit: String = "v1", proofs: List<String> = emptyList()) = PendingAction(
        userId = user, visitId = visit, actionType = PendingAction.TYPE_PAYMENT_CREATE,
        latitude = 0.0, longitude = 0.0, paymentPayload = payload(key, proofs)
    )

    private class Env(initialFiles: Map<String, ByteArray> = emptyMap()) {
        val api = FakeCollectionApi()
        val queue = OfflineQueueManager(InMemorySharedPreferences())
        val deleted = mutableListOf<String>()
        val files = initialFiles.toMutableMap()
        val processor = PaymentQueueProcessor(api, queue, { files[it] }, { deleted += it; files.remove(it) })
    }

    // ---------------------------------------------------------------- processor

    @Test
    fun replay_createsWithSameKey_uploadsProofs_removesFromQueue() = runBlocking {
        val e = Env(mapOf("/p/1.jpg" to byteArrayOf(1, 2, 3)))
        val action = payAction(proofs = listOf("/p/1.jpg"))
        e.queue.enqueueAction(action)

        val out = e.processor.replay(action)

        assertEquals(PaymentReplayOutcome.Synced, out)
        assertEquals("key-1", e.api.createCalls.single().idempotencyKey)
        assertEquals("v1", e.api.createCalls.single().visitId)
        assertEquals(1, e.api.proofUploadCalls)
        assertTrue(e.queue.getQueue().isEmpty())
        assertEquals(listOf("/p/1.jpg"), e.deleted)
    }

    @Test
    fun networkFailureThenRetry_reusesTheSameKey_andCreatesExactlyOnePayment() = runBlocking {
        val e = Env()
        val action = payAction()
        e.queue.enqueueAction(action)
        e.api.createThrows = IOException("no network")

        assertEquals(PaymentReplayOutcome.Retry, e.processor.replay(action))
        assertEquals(1, e.queue.getQueue().size)

        e.api.createThrows = null
        assertEquals(PaymentReplayOutcome.Synced, e.processor.replay(e.queue.getQueue().single()))
        assertEquals(setOf("key-1"), e.api.createCalls.map { it.idempotencyKey }.toSet())
        assertEquals("backend dedup store holds one payment", 1, e.api.storedPayments.size)
        assertTrue(e.queue.getQueue().isEmpty())
    }

    @Test
    fun replayAfterTimeoutWhereServerAlreadyCreated_returnsExistingRecord_noDuplicate() = runBlocking {
        val e = Env()
        val action = payAction()
        // First attempt reached the server but the response was lost.
        e.api.createPayment(action.paymentPayload!!.toRequest(action.visitId))
        e.queue.enqueueAction(action)

        assertEquals(PaymentReplayOutcome.Synced, e.processor.replay(action))
        assertEquals(1, e.api.storedPayments.size)
    }

    @Test
    fun serverErrors5xxAnd408And429_retry() = runBlocking {
        for (code in listOf(500, 503, 408, 429)) {
            val e = Env()
            val action = payAction()
            e.queue.enqueueAction(action)
            e.api.createBehavior = { e.api.err(code) }
            assertEquals("code $code", PaymentReplayOutcome.Retry, e.processor.replay(action))
            assertEquals(1, e.queue.getQueue().size)
        }
    }

    @Test
    fun validationRejections400_409_422_becomeConflictWithServerMessage() = runBlocking {
        for (code in listOf(400, 409, 422)) {
            val e = Env()
            val action = payAction()
            e.queue.enqueueAction(action)
            e.api.createBehavior = { e.api.err(code, """{"error":{"code":"X","message":"Cheque number already used"}}""") }

            val out = e.processor.replay(action)

            out as PaymentReplayOutcome.Conflict
            assertEquals(ConflictType.SERVER_REJECTED, out.conflict.conflictType)
            assertTrue(out.conflict.message, out.conflict.message.contains("Cheque number already used"))
            assertTrue(out.conflict.message.contains(code.toString()))
            e.queue.moveToConflict(out.conflict)
            assertTrue("never retried forever", e.queue.getQueue().isEmpty())
            assertEquals(1, e.queue.getConflictsForUser(user).size)
        }
    }

    @Test
    fun notFound404_becomesVisitOrOutletUnavailableConflict() = runBlocking {
        val e = Env()
        val action = payAction()
        e.api.createBehavior = { e.api.err(404) }
        val out = e.processor.replay(action) as PaymentReplayOutcome.Conflict
        assertEquals(ConflictType.VISIT_UNAVAILABLE, out.conflict.conflictType)
        assertEquals(SyncErrorPolicy.PAYMENT_NOT_AVAILABLE_MESSAGE, out.conflict.message)
        assertTrue(out.conflict.message.contains("no longer available"))
    }

    @Test
    fun unauthorized401_pausesAndKeepsQueue() = runBlocking {
        val e = Env()
        val action = payAction()
        e.queue.enqueueAction(action)
        e.api.createBehavior = { e.api.err(401) }
        assertEquals(PaymentReplayOutcome.AuthExpired, e.processor.replay(action))
        assertEquals(1, e.queue.getQueue().size)
    }

    @Test
    fun proofFailureAfterCreate_doesNotRecreatePayment_andResumesProofsOnly() = runBlocking {
        val e = Env(mapOf("/p/1.jpg" to byteArrayOf(1), "/p/2.jpg" to byteArrayOf(2)))
        val action = payAction(proofs = listOf("/p/1.jpg", "/p/2.jpg"))
        e.queue.enqueueAction(action)
        // proof 1 ok, proof 2 network failure
        var n = 0
        e.api.proofBehavior = { if (++n == 2) throw IOException("drop") else null }

        assertEquals(PaymentReplayOutcome.Retry, e.processor.replay(action))
        val saved = e.queue.getQueue().single()
        assertNotNull(saved.paymentPayload?.serverPaymentId)
        assertEquals(listOf("/p/2.jpg"), saved.paymentPayload?.proofPaths)

        e.api.proofBehavior = { null }
        assertEquals(PaymentReplayOutcome.Synced, e.processor.replay(saved))
        assertEquals("payment created once", 1, e.api.createCalls.size)
        assertTrue(e.queue.getQueue().isEmpty())
    }

    @Test
    fun rejectedProof_isReportedButPaymentStaysRecorded() = runBlocking {
        val e = Env(mapOf("/p/1.jpg" to byteArrayOf(1)))
        val action = payAction(proofs = listOf("/p/1.jpg"))
        e.queue.enqueueAction(action)
        e.api.proofBehavior = { e.api.proofErr(422, """{"error":{"message":"Unsupported image"}}""") }

        val out = e.processor.replay(action) as PaymentReplayOutcome.Conflict
        assertTrue(out.conflict.message.contains("Payment was recorded"))
        assertTrue(out.conflict.message.contains("Unsupported image"))
        assertTrue(e.queue.getQueue().isEmpty())
        assertEquals(1, e.api.createCalls.size)
    }

    @Test
    fun missingPayload_isAConflictNotAnInfiniteRetry() = runBlocking {
        val e = Env()
        val broken = PendingAction(userId = user, visitId = "v1", actionType = "PAYMENT_CREATE", latitude = 0.0, longitude = 0.0)
        assertTrue(e.processor.replay(broken) is PaymentReplayOutcome.Conflict)
    }

    // ---------------------------------------------------------------- submitter (form -> queue)

    private fun submitter(api: FakeCollectionApi, queue: OfflineQueueManager, files: Map<String, ByteArray> = emptyMap()) =
        PaymentSubmitter(CollectionRepository(api), queue, { files[it] }, { })

    private suspend fun PaymentSubmitter.go(key: String = "form-key", proofs: List<String> = emptyList(), userId: String? = user) =
        submit(
            userId = userId, visitId = "v1", customerId = "c1", outletName = "Sharma Store", idempotencyKey = key,
            invoiceId = null, amount = "2500.0", paymentMethod = "CASH", paymentDate = "2026-10-10",
            chequeNumber = null, chequeBankName = null, utrReference = null, notes = null,
            allocations = listOf(BrandAllocationInput("BrandA", 2500.0)), proofPaths = proofs
        )

    @Test
    fun noConnectivity_savesOffline_withStableKeyAndProofPaths_notAnError() = runBlocking {
        val api = FakeCollectionApi().apply { createThrows = IOException("Unable to resolve host") }
        val queue = OfflineQueueManager(InMemorySharedPreferences())
        val out = submitter(api, queue).go(proofs = listOf("/private/p1.jpg"))

        out as PaymentSubmitOutcome.SavedOffline
        val queued = queue.getQueueForUser(user).single()
        assertEquals(PendingAction.TYPE_PAYMENT_CREATE, queued.actionType)
        assertEquals("form-key", queued.paymentPayload?.idempotencyKey)
        assertEquals(listOf("/private/p1.jpg"), queued.paymentPayload?.proofPaths)
        assertEquals("Sharma Store", queued.paymentPayload?.outletName)
        assertEquals("2500.0", queued.paymentPayload?.amount)
        assertEquals(user, queued.userId)
    }

    @Test
    fun serverError5xx_savesOffline_butValidationErrorIsShownAndNotQueued() = runBlocking {
        val queue = OfflineQueueManager(InMemorySharedPreferences())
        val api = FakeCollectionApi()
        api.createBehavior = { api.err(503) }
        assertTrue(submitter(api, queue).go() is PaymentSubmitOutcome.SavedOffline)
        assertEquals(1, queue.getQueue().size)

        val q2 = OfflineQueueManager(InMemorySharedPreferences())
        val api2 = FakeCollectionApi()
        api2.createBehavior = { api2.err(422, "{}") }
        val rej = submitter(api2, q2).go()
        assertTrue(rej is PaymentSubmitOutcome.Rejected)
        assertEquals(422, (rej as PaymentSubmitOutcome.Rejected).code)
        assertTrue(q2.getQueue().isEmpty())
    }

    @Test
    fun offlineThenOnlineRetryWithSameKey_producesExactlyOnePayment() = runBlocking {
        val api = FakeCollectionApi()
        val queue = OfflineQueueManager(InMemorySharedPreferences())
        api.createThrows = IOException("timeout")
        submitter(api, queue).go(key = "K")
        // user (or double-tap) resubmits the same logical form after the server already got it once
        api.createThrows = null
        assertTrue(submitter(api, queue).go(key = "K") is PaymentSubmitOutcome.Created)
        // ...and the queued copy later replays: still a single server payment, one queue entry per key
        val queued = queue.getQueue().single()
        assertEquals(PaymentReplayOutcome.Synced, PaymentQueueProcessor(api, queue).replay(queued))
        assertEquals(1, api.storedPayments.size)
        assertEquals(setOf("K"), api.createCalls.map { it.idempotencyKey }.toSet())
    }

    @Test
    fun onlineSuccessButProofUploadFails_queuesOnlyTheProofWork() = runBlocking {
        val api = FakeCollectionApi()
        api.proofThrows = IOException("drop")
        val queue = OfflineQueueManager(InMemorySharedPreferences())
        val out = submitter(api, queue, mapOf("/p.jpg" to byteArrayOf(9))).go(proofs = listOf("/p.jpg"))
        out as PaymentSubmitOutcome.CreatedProofsQueued
        val q = queue.getQueue().single()
        assertEquals(out.payment.id, q.paymentPayload?.serverPaymentId)
        assertEquals(listOf("/p.jpg"), q.paymentPayload?.proofPaths)
    }

    @Test
    fun notSignedIn_cannotQueue_andIsReportedAsFailure() = runBlocking {
        val api = FakeCollectionApi().apply { createThrows = IOException("x") }
        val queue = OfflineQueueManager(InMemorySharedPreferences())
        assertTrue(submitter(api, queue).go(userId = null) is PaymentSubmitOutcome.Rejected)
        assertTrue(queue.getQueue().isEmpty())
    }

    // ---------------------------------------------------------------- queue storage

    @Test
    fun twoDifferentPaymentsOnSameVisit_bothKept_sameKeyReplaced() {
        val q = OfflineQueueManager(InMemorySharedPreferences())
        q.enqueueAction(payAction(key = "A"))
        q.enqueueAction(payAction(key = "B"))
        assertEquals(2, q.getQueue().size)
        q.enqueueAction(payAction(key = "A"))
        assertEquals(2, q.getQueue().size)
    }

    @Test
    fun paymentSurvivesJsonRoundTrip_andOldEntriesWithoutPayloadStillParse() {
        val prefs = InMemorySharedPreferences()
        val q = OfflineQueueManager(prefs)
        q.enqueueAction(payAction(key = "RT", proofs = listOf("/p/a.jpg")))
        val reread = OfflineQueueManager(prefs).getQueueForUser(user).single()
        assertEquals("RT", reread.paymentPayload?.idempotencyKey)
        assertEquals(1, reread.paymentPayload?.allocations?.size)

        val json = prefs.getString("pending_queue", "")!!
        assertTrue(json.contains("\"paymentPayload\""))
        assertTrue(json.contains("\"idempotencyKey\":\"RT\""))

        val old = InMemorySharedPreferences()
        old.edit().putString(
            "pending_queue",
            """[{"id":"x","userId":"u1","visitId":"v","actionType":"CHECK_IN","latitude":1.0,"longitude":2.0,"timestamp":5}]"""
        ).apply()
        val a = OfflineQueueManager(old).getQueueForUser("u1").single()
        assertNull(a.paymentPayload)
        assertTrue(!a.isPayment)
    }

    @Test
    fun updateAction_isUserNeutralInPlaceReplace() {
        val q = OfflineQueueManager(InMemorySharedPreferences())
        val a = payAction()
        q.enqueueAction(a)
        q.updateAction(a.copy(paymentPayload = a.paymentPayload!!.copy(serverPaymentId = "S")))
        assertEquals("S", q.getQueue().single().paymentPayload?.serverPaymentId)
        q.removeAction(a.id)
        q.updateAction(a)
        assertTrue(q.getQueue().isEmpty())
    }

    // ---------------------------------------------------------------- sync ordering (VisitRepository)

    private inline fun <reified T> stub(crossinline handler: (String) -> Any?): T =
        Proxy.newProxyInstance(T::class.java.classLoader, arrayOf(T::class.java)) { _, m, args ->
            when (m.name) {
                "toString" -> "stub"
                "hashCode" -> 1
                "equals" -> false
                else -> handler(m.name + ":" + (args?.firstOrNull() ?: ""))
            }
        } as T

    private fun repo(api: FakeCollectionApi, queue: OfflineQueueManager, checkOut: () -> Any?): VisitRepository {
        val visitApi = stub<VisitApi> { call ->
            when {
                call.startsWith("getVisitById") -> { api.log += call; Response.error<Any>(500, "{}".toResponseBody("application/json".toMediaTypeOrNull())) }
                call.startsWith("checkOut") -> { api.log += call; checkOut() }
                else -> throw IllegalStateException("unexpected $call")
            }
        }
        return VisitRepository(
            visitApi = visitApi,
            customerApi = stub<CustomerApi> { null },
            geoApi = stub<GeoApi> { null },
            offlineQueueManager = queue,
            collectionApi = api
        )
    }

    private fun checkOutAction(visit: String) =
        PendingAction(userId = user, visitId = visit, actionType = "CHECK_OUT", latitude = 1.0, longitude = 2.0)

    @Test
    fun sync_replaysPaymentsAfterCheckOut_evenWhenCapturedBefore() = runBlocking {
        val api = FakeCollectionApi()
        val queue = OfflineQueueManager(InMemorySharedPreferences())
        queue.enqueueAction(payAction(key = "K1", visit = "v1")) // captured first
        queue.enqueueAction(checkOutAction("v1"))
        val r = repo(api, queue) { Response.error<Any>(409, "{}".toResponseBody("application/json".toMediaTypeOrNull())) }

        r.syncOfflineQueue(activeUserId = user)

        val iCheckOut = api.log.indexOf("checkOut:v1")
        val iPay = api.log.indexOf("createPayment:v1")
        assertTrue(api.log.toString(), iCheckOut >= 0 && iPay >= 0)
        assertTrue("check-out must run before the payment: ${api.log}", iCheckOut < iPay)
    }

    @Test
    fun sync_holdsPaymentWhileItsVisitCheckOutIsStillFailingTransiently_butSyncsOthers() = runBlocking {
        val api = FakeCollectionApi()
        val queue = OfflineQueueManager(InMemorySharedPreferences())
        queue.enqueueAction(payAction(key = "K1", visit = "v1"))
        queue.enqueueAction(checkOutAction("v1"))
        queue.enqueueAction(payAction(key = "K2", visit = "v2"))
        val r = repo(api, queue) { throw IOException("offline") }

        val result = r.syncOfflineQueue(activeUserId = user)

        assertTrue("v1 payment waits for its check-out", api.createCalls.none { it.visitId == "v1" })
        assertEquals(listOf("v2"), api.createCalls.map { it.visitId })
        assertEquals(1, result.syncedCount)
        assertTrue(result.retryableFailures >= 2)
        assertEquals(setOf("K1"), queue.getQueue().mapNotNull { it.paymentPayload?.idempotencyKey }.toSet())
    }

    @Test
    fun sync_paymentConflictIsMovedOutOfQueueAndVisibleToUser() = runBlocking {
        val api = FakeCollectionApi()
        api.createBehavior = { api.err(422, """{"error":{"message":"Amount exceeds outstanding"}}""") }
        val queue = OfflineQueueManager(InMemorySharedPreferences())
        queue.enqueueAction(payAction(key = "K1"))
        val r = repo(api, queue) { null }

        val result = r.syncOfflineQueue(activeUserId = user)

        assertEquals(1, result.conflicts.size)
        assertTrue(queue.getQueueForUser(user).isEmpty())
        val shown = queue.getConflictsForUser(user).single()
        assertTrue(shown.message.contains("Amount exceeds outstanding"))
        assertEquals(1, api.createCalls.size)
        // running the sync again never retries a conflicted payment
        r.syncOfflineQueue(activeUserId = user)
        assertEquals(1, api.createCalls.size)
        assertNotEquals(0, result.conflicts.size)
    }

    @Test
    fun sync_unauthorizedPausesAndKeepsPayment() = runBlocking {
        val api = FakeCollectionApi()
        api.createBehavior = { api.err(401) }
        val queue = OfflineQueueManager(InMemorySharedPreferences())
        queue.enqueueAction(payAction(key = "K1"))
        val result = repo(api, queue) { null }.syncOfflineQueue(activeUserId = user)
        assertTrue(result.pausedForAuth)
        assertEquals(1, queue.getQueueForUser(user).size)
    }

    @Test
    fun workdayOfflineFallback_readsOnlyCurrentUsersQueue() = runBlocking {
        val queue = OfflineQueueManager(InMemorySharedPreferences())
        queue.enqueueAction(
            PendingAction(userId = "other", visitId = "workday", actionType = "START_DAY", latitude = 1.0, longitude = 2.0)
        )
        val tokens = com.fieldtrackpro.android.data.local.TokenManager(null, InMemorySharedPreferences())
        tokens.saveUserProfile("Me", null, "EMPLOYEE", id = "me")
        val api = stub<com.fieldtrackpro.android.data.api.WorkdayApi> { throw IOException("offline") }
        val repo = WorkdayRepository(api, queue, tokens)

        val noOwn = repo.getTodayWorkday()
        assertTrue("other employee's START_DAY must not appear: $noOwn", noOwn is Resource.Error<*> || (noOwn as Resource.Success).data.session == null)

        queue.enqueueAction(
            PendingAction(userId = "me", visitId = "workday", actionType = "START_DAY", latitude = 1.0, longitude = 2.0)
        )
        val own = repo.getTodayWorkday() as Resource.Success
        assertEquals("STARTED", own.data.session?.status)
    }
}
