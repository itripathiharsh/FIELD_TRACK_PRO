package com.fieldtrackpro.android.data.outletproof

import com.fieldtrackpro.android.data.local.InMemorySharedPreferences
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.OutletProofDraftStore
import com.fieldtrackpro.android.data.local.OutletProofPayload
import com.fieldtrackpro.android.data.local.PendingAction
import com.fieldtrackpro.android.data.model.OutletProofRead
import com.fieldtrackpro.android.data.repository.OutletProofMessages
import com.fieldtrackpro.android.data.repository.OutletProofOutcome
import com.fieldtrackpro.android.data.repository.OutletProofSubmitter
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException

class OutletProofSubmitterTest {
    private val user = "u1"
    private val photo = byteArrayOf(1, 2, 3, 4)

    private fun payload(key: String = "key-12345678", customerId: String? = "c1", path: String = "/p/1.jpg") = OutletProofPayload(
        idempotencyKey = key, customerId = customerId, outletName = "Sharma Store", photoPath = path,
        latitude = 28.6139391, longitude = 77.2090212, accuracyM = 12.5,
        capturedAt = "2026-10-13T16:25:01.123+05:30", capturedAtEpochMs = 1_000L, isMock = false, deviceInfo = "Pixel 7"
    )

    private class Env(files: Map<String, ByteArray>) {
        val api = FakeOutletProofApi()
        val queue = OfflineQueueManager(InMemorySharedPreferences())
        val deleted = mutableListOf<String>()
        val submitter = OutletProofSubmitter(api, queue, { files[it] }, { deleted += it })
    }

    private fun env() = Env(mapOf("/p/1.jpg" to photo, "/p/2.jpg" to photo))

    @Test
    fun online_success_returnsProof_andSendsOneBundle() = runBlocking {
        val e = env()
        val out = e.submitter.submit(user, payload())
        out as OutletProofOutcome.Uploaded
        assertEquals("PENDING", out.proof.status)
        val up = e.api.uploads.single()
        assertEquals("c1", up.fields["customer_id"])
        assertEquals(photo.toList(), up.photoBytes?.toList())
        assertTrue(e.queue.getQueue().isEmpty())
    }

    @Test
    fun newOutlet_omitsCustomerId_andStoresUnattached() = runBlocking {
        val e = env()
        val out = e.submitter.submit(user, payload(customerId = null)) as OutletProofOutcome.Uploaded
        assertEquals("UNATTACHED", out.proof.status)
        assertFalse(e.api.uploads.single().fields.containsKey("customer_id"))
    }

    @Test
    fun existingOutlet_offline_isQueuedWithPayload_notAnError() = runBlocking {
        val e = env()
        e.api.throwsOnUpload = IOException("Unable to resolve host")
        val out = e.submitter.submit(user, payload()) as OutletProofOutcome.SavedOffline
        val q = e.queue.getQueueForUser(user).single()
        assertEquals(out.action.id, q.id)
        assertEquals(PendingAction.TYPE_OUTLET_PROOF, q.actionType)
        assertEquals("key-12345678", q.outletProofPayload?.idempotencyKey)
        assertEquals("/p/1.jpg", q.outletProofPayload?.photoPath)
        assertEquals("c1", q.outletProofPayload?.customerId)
        assertEquals(user, q.userId)
    }

    @Test
    fun transientHttp_5xx_408_429_areQueued() = runBlocking {
        for (code in listOf(500, 503, 408, 429)) {
            val e = env()
            e.api.behavior = { e.api.err(code) }
            assertTrue("code $code", e.submitter.submit(user, payload()) is OutletProofOutcome.SavedOffline)
            assertEquals(1, e.queue.getQueue().size)
        }
    }

    @Test
    fun newOutlet_offline_isNeverQueued_needsInternet() = runBlocking {
        val e = env()
        e.api.throwsOnUpload = IOException("offline")
        val out = e.submitter.submit(user, payload(customerId = null))
        out as OutletProofOutcome.NeedsInternet
        assertTrue(out.message.contains("Internet needed to add a new outlet"))
        assertTrue(e.queue.getQueue().isEmpty())
    }

    @Test
    fun stale422_onlineIsRejectedWithRetake_andNotQueued() = runBlocking {
        val e = env()
        e.api.behavior = { e.api.errCode(422, "OUTLET_PROOF_STALE_CAPTURE", "too old") }
        val out = e.submitter.submit(user, payload()) as OutletProofOutcome.Rejected
        assertTrue(out.retakeRequired)
        assertEquals("OUTLET_PROOF_STALE_CAPTURE", out.errorCode)
        assertEquals(OutletProofMessages.STALE_CAPTURE, out.message)
        assertTrue(e.queue.getQueue().isEmpty())
    }

    @Test
    fun conflictCodes_409_areFriendly() = runBlocking {
        val pending = env().also { env -> env.api.behavior = { env.api.errCode(409, "OUTLET_PROOF_ALREADY_PENDING") } }
        val a = pending.submitter.submit(user, payload()) as OutletProofOutcome.Rejected
        assertTrue(a.message, a.message.contains("waiting for admin review"))
        assertFalse(a.retakeRequired)

        val dup = env().also { env -> env.api.behavior = { env.api.errCode(409, "OUTLET_PROOF_DUPLICATE_IMAGE") } }
        val b = dup.submitter.submit(user, payload()) as OutletProofOutcome.Rejected
        assertTrue(b.message, b.message.contains("already used for another outlet"))
        assertTrue(b.retakeRequired)

        val confirmed = env().also { env -> env.api.behavior = { env.api.errCode(409, "OUTLET_PROOF_ALREADY_CONFIRMED") } }
        val c = confirmed.submitter.submit(user, payload()) as OutletProofOutcome.Rejected
        assertTrue(c.message.contains("already confirmed"))
    }

    @Test
    fun otherRejections_mapToFriendlyMessages() = runBlocking {
        val cases = mapOf(
            "OUTLET_PROOF_MOCK_LOCATION" to "Mock/fake location",
            "OUTLET_PROOF_ACCURACY_TOO_LOW" to "within 30 m",
            "OUTLET_PROOF_FUTURE_CAPTURE" to "clock",
            "OUTLET_PROOF_OUTSIDE_INDIA" to "outside India"
        )
        for ((code, fragment) in cases) {
            val e = env().also { env -> env.api.behavior = { env.api.errCode(422, code) } }
            val out = e.submitter.submit(user, payload()) as OutletProofOutcome.Rejected
            assertTrue("$code -> ${out.message}", out.message.contains(fragment))
            assertTrue(out.retakeRequired)
        }
        val e415 = env().also { env -> env.api.behavior = { env.api.err(415) } }
        assertTrue((e415.submitter.submit(user, payload()) as OutletProofOutcome.Rejected).retakeRequired)
        val e404 = env().also { env -> env.api.behavior = { env.api.errCode(404, "CUSTOMER_NOT_FOUND") } }
        val nf = e404.submitter.submit(user, payload()) as OutletProofOutcome.Rejected
        assertTrue(nf.message.contains("no longer available"))
    }

    @Test
    fun missingPhotoFile_isRejectedWithRetake_beforeAnyNetworkCall() = runBlocking {
        val e = env()
        val out = e.submitter.submit(user, payload(path = "/gone.jpg")) as OutletProofOutcome.Rejected
        assertTrue(out.retakeRequired)
        assertTrue(e.api.uploads.isEmpty())
    }

    @Test
    fun oversizedPhoto_isRejectedLocally() = runBlocking {
        val big = ByteArray(10 * 1024 * 1024 + 1)
        val e = Env(mapOf("/p/1.jpg" to big))
        val out = e.submitter.submit(user, payload()) as OutletProofOutcome.Rejected
        assertTrue(out.retakeRequired)
        assertTrue(e.api.uploads.isEmpty())
    }

    @Test
    fun idempotencyKey_isStableAcrossRetries_andServerStoresOneProof() = runBlocking {
        val e = env()
        e.api.throwsOnUpload = IOException("drop")
        e.submitter.submit(user, payload(key = "STABLE-KEY-1"))
        e.api.throwsOnUpload = null
        val queued = e.queue.getQueue().single().outletProofPayload!!
        e.submitter.submit(user, queued)
        e.submitter.submit(user, queued)
        assertEquals(setOf("STABLE-KEY-1"), e.api.uploads.map { it.fields["idempotency_key"] }.toSet())
        assertEquals(1, e.api.stored.size)
    }

    @Test
    fun idempotencyKey_survivesProcessDeath_viaDraftStore() {
        val prefs = InMemorySharedPreferences()
        OutletProofDraftStore(prefs).save(user, payload(key = "DRAFT-KEY-123"))
        // "process death": a brand new store instance over the same persisted prefs
        val restored = OutletProofDraftStore(prefs).get(user, "c1")
        assertNotNull(restored)
        assertEquals("DRAFT-KEY-123", restored!!.idempotencyKey)
        assertEquals("/p/1.jpg", restored.photoPath)
        assertEquals(setOf("/p/1.jpg"), OutletProofDraftStore(prefs).allPhotoPaths())
        OutletProofDraftStore(prefs).clear(user, "c1")
        assertNull(OutletProofDraftStore(prefs).get(user, "c1"))
    }

    @Test
    fun draftScopes_areSeparatePerOutletAndPerUser() {
        val store = OutletProofDraftStore(InMemorySharedPreferences())
        store.save("a", payload(key = "KEY-AAAAAAAA", customerId = null))
        store.save("a", payload(key = "KEY-BBBBBBBB", customerId = "c9"))
        assertEquals("KEY-AAAAAAAA", store.get("a", null)?.idempotencyKey)
        assertEquals("KEY-BBBBBBBB", store.get("a", "c9")?.idempotencyKey)
        assertNull(store.get("b", null))
    }

    @Test
    fun newerCaptureSupersedesAnUnsentQueuedOneForTheSameOutlet() = runBlocking {
        val e = env()
        e.api.throwsOnUpload = IOException("offline")
        e.submitter.submit(user, payload(key = "KEY-FIRST-01", path = "/p/1.jpg"))
        e.submitter.submit(user, payload(key = "KEY-SECOND-2", path = "/p/2.jpg"))
        val q = e.queue.getQueue().single()
        assertEquals("KEY-SECOND-2", q.outletProofPayload?.idempotencyKey)
        assertEquals(listOf("/p/1.jpg"), e.deleted)
    }

    @Test
    fun notSignedIn_cannotQueue_andIsReported() = runBlocking {
        val e = env()
        e.api.throwsOnUpload = IOException("x")
        assertTrue(e.submitter.submit(null, payload()) is OutletProofOutcome.Rejected)
        assertTrue(e.queue.getQueue().isEmpty())
    }

    @Test
    fun describeResult_coversConfirmationChangeAndInitial() {
        val base = OutletProofRead(id = "p")
        assertTrue(OutletProofMessages.describeResult(base.copy(kind = "CONFIRMATION", status = "CONFIRMED")).contains("confirmed"))
        assertTrue(
            OutletProofMessages.describeResult(base.copy(kind = "CHANGE_REQUEST", status = "PENDING", distanceFromVerifiedM = 120.0))
                .contains("120 m")
        )
        assertTrue(OutletProofMessages.describeResult(base.copy(kind = "INITIAL", status = "PENDING")).contains("Pending admin approval"))
    }
}
