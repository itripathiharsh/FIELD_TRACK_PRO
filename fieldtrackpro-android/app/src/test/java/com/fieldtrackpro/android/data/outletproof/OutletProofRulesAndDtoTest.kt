package com.fieldtrackpro.android.data.outletproof

import com.fieldtrackpro.android.data.local.LogoutDecision
import com.fieldtrackpro.android.data.local.LogoutPolicy
import com.fieldtrackpro.android.data.local.OutletProofPayload
import com.fieldtrackpro.android.data.local.OutletProofStore
import com.fieldtrackpro.android.data.local.PendingAction
import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.data.model.CustomerProspectCreate
import com.fieldtrackpro.android.data.model.OutletProofRead
import com.fieldtrackpro.android.data.remote.OutletProofMultipart
import com.fieldtrackpro.android.utils.AccuracyBand
import com.fieldtrackpro.android.utils.OutletProofRules
import com.fieldtrackpro.android.utils.ProofFix
import com.fieldtrackpro.android.utils.ShutterBlock
import com.fieldtrackpro.android.utils.ShutterState
import com.google.gson.Gson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files
import java.time.ZoneId
import java.time.ZoneOffset

class OutletProofRulesAndDtoTest {

    private fun fix(acc: Float = 12f, at: Long = 100_000L, mock: Boolean = false) =
        ProofFix(28.6, 77.2, acc, at, mock)

    // ------------------------------------------------------------ shutter enablement

    @Test
    fun shutter_readyOnlyWhenAccurateFreshAndNotMock() {
        assertTrue(OutletProofRules.evaluate(fix(), 101_000L) is ShutterState.Ready)
        assertTrue(OutletProofRules.evaluate(fix(acc = 30f), 101_000L) is ShutterState.Ready)
        assertTrue("exactly 10 s old is still fresh", OutletProofRules.evaluate(fix(), 110_000L) is ShutterState.Ready)
    }

    @Test
    fun shutter_blocked_noFix_accuracy_stale_mock() {
        assertEquals(ShutterState.Blocked(ShutterBlock.NO_FIX), OutletProofRules.evaluate(null, 1L))
        assertEquals(ShutterState.Blocked(ShutterBlock.ACCURACY_TOO_LOW), OutletProofRules.evaluate(fix(acc = 30.1f), 101_000L))
        assertEquals(ShutterState.Blocked(ShutterBlock.ACCURACY_TOO_LOW), OutletProofRules.evaluate(fix(acc = Float.NaN), 101_000L))
        assertEquals(ShutterState.Blocked(ShutterBlock.STALE_FIX), OutletProofRules.evaluate(fix(), 110_001L))
        assertEquals(ShutterState.Blocked(ShutterBlock.MOCK_LOCATION), OutletProofRules.evaluate(fix(mock = true), 101_000L))
    }

    @Test
    fun shutter_aFixThatAgesOutDisablesTheShutterAgain() {
        val f = fix(at = 0L)
        assertTrue(OutletProofRules.evaluate(f, 5_000L) is ShutterState.Ready)
        assertTrue(OutletProofRules.evaluate(f, 15_000L) is ShutterState.Blocked)
    }

    @Test
    fun blockedTextsMatchTheSpec() {
        assertEquals("Waiting for better GPS…", OutletProofRules.blockMessage(ShutterBlock.ACCURACY_TOO_LOW))
    }

    @Test
    fun accuracyBands() {
        assertEquals(AccuracyBand.GOOD, OutletProofRules.band(20f))
        assertEquals(AccuracyBand.FAIR, OutletProofRules.band(20.5f))
        assertEquals(AccuracyBand.FAIR, OutletProofRules.band(30f))
        assertEquals(AccuracyBand.POOR, OutletProofRules.band(30.5f))
        assertEquals(AccuracyBand.NONE, OutletProofRules.band(null))
    }

    @Test
    fun uploadFreshness_andUnattachedValidity() {
        assertTrue(OutletProofRules.isUploadFresh(1_000_000L, 1_000_000L + 149_000L))
        assertFalse(OutletProofRules.isUploadFresh(1_000_000L, 1_000_000L + 151_000L))
        assertFalse(OutletProofRules.isUploadFresh(1_000_000L, 1_000_000L - 61_000L))
        assertFalse(OutletProofRules.isUploadFresh(null, 5L))
        assertTrue(OutletProofRules.isUnattachedProofUsable(0L, 46L * 3600_000))
        assertFalse(OutletProofRules.isUnattachedProofUsable(0L, 48L * 3600_000))
        assertFalse(OutletProofRules.isUnattachedProofUsable(null, 0L))
    }

    @Test
    fun capturedAt_isIsoWithOffsetAndMilliseconds() {
        // 2026-10-13T10:55:01.123Z == 16:25:01.123 in IST (+05:30)
        val epoch = java.time.Instant.parse("2026-10-13T10:55:01.123Z").toEpochMilli()
        assertEquals("2026-10-13T16:25:01.123+05:30", OutletProofRules.isoWithOffset(epoch, ZoneId.of("Asia/Kolkata")))
        assertEquals("2026-10-13T10:55:01.123Z", OutletProofRules.isoWithOffset(epoch, ZoneOffset.UTC))
    }

    // ------------------------------------------------------------ multipart / DTO serialization

    @Test
    fun multipart_fieldNamesAndValues_matchTheBackendContract() {
        val p = OutletProofPayload(
            idempotencyKey = "key-12345678", customerId = "7f0c1d2e-0000-4000-8000-000000000001", photoPath = "/x.jpg",
            latitude = 28.6139391, longitude = 77.2090212, accuracyM = 12.5,
            capturedAt = "2026-10-13T16:25:01.123+05:30", isMock = false, deviceInfo = "Pixel 7"
        )
        val rec = FakeOutletProofApi.decode(OutletProofMultipart.build(p, byteArrayOf(9, 9)))
        assertEquals("<file:outlet_proof.jpg:2>", rec.fields["photo"])
        assertEquals("28.6139391", rec.fields["latitude"])
        assertEquals("77.2090212", rec.fields["longitude"])
        assertEquals("12.50", rec.fields["accuracy_m"])
        assertEquals("2026-10-13T16:25:01.123+05:30", rec.fields["captured_at"])
        assertEquals("false", rec.fields["is_mock_location"])
        assertEquals("key-12345678", rec.fields["idempotency_key"])
        assertEquals("Pixel 7", rec.fields["device_info"])
        assertEquals("7f0c1d2e-0000-4000-8000-000000000001", rec.fields["customer_id"])
        assertEquals(
            setOf("photo", "latitude", "longitude", "accuracy_m", "captured_at", "is_mock_location", "idempotency_key", "device_info", "customer_id"),
            rec.fields.keys
        )
    }

    @Test
    fun multipart_newOutlet_omitsCustomerId_and_mockIsTrueString() {
        val p = OutletProofPayload(
            idempotencyKey = "key-12345678", customerId = null, latitude = 1.0, longitude = 2.0,
            accuracyM = 5.0, capturedAt = "2026-10-13T10:55:01.123Z", isMock = true
        )
        val rec = FakeOutletProofApi.decode(OutletProofMultipart.build(p, byteArrayOf(1)))
        assertFalse(rec.fields.containsKey("customer_id"))
        assertFalse(rec.fields.containsKey("device_info"))
        assertEquals("true", rec.fields["is_mock_location"])
    }

    @Test
    fun deviceInfo_isCappedAt200() {
        val p = OutletProofPayload(idempotencyKey = "key-12345678", deviceInfo = "x".repeat(500))
        assertEquals(200, FakeOutletProofApi.decode(OutletProofMultipart.build(p, byteArrayOf(1))).fields["device_info"]!!.length)
    }

    @Test
    fun prospectRequest_carriesOutletProofId_withSnakeCaseName() {
        val json = Gson().toJson(CustomerProspectCreate(name = "A", contactNumber = "9", outletProofId = "pid-1"))
        assertTrue(json, json.contains("\"outlet_proof_id\":\"pid-1\""))
        assertTrue(json.contains("\"contact_number\":\"9\""))
        assertTrue(json.contains("\"force\":false"))
    }

    @Test
    fun outletProofRead_and_customerDto_parseServerJson() {
        val proof = Gson().fromJson(
            """{"id":"p1","customer_id":"c1","prospect_id":null,"kind":"CHANGE_REQUEST","status":"PENDING","is_primary":false,
               "latitude":28.1,"longitude":77.1,"accuracy_m":9.5,"captured_at":"2026-10-13T16:25:01.123+05:30",
               "distance_from_verified_m":143.2,"image_url":null,"extra_field_we_ignore":1}""",
            OutletProofRead::class.java
        )
        assertEquals("CHANGE_REQUEST", proof.kind)
        assertEquals(143.2, proof.distanceFromVerifiedM!!, 0.001)
        assertEquals(9.5, proof.accuracyM!!, 0.001)

        val dto = Gson().fromJson(
            """{"id":"c1","name":"X","primary_outlet_image_available":true,"primary_outlet_proof_id":"p9"}""", CustomerDto::class.java
        )
        assertTrue(dto.primaryOutletImageAvailable)
        assertEquals("p9", dto.primaryOutletProofId)
        val old = Gson().fromJson("""{"id":"c1","name":"X"}""", CustomerDto::class.java)
        assertFalse(old.primaryOutletImageAvailable)
    }

    // ------------------------------------------------------------ logout policy / store

    private fun act(type: String, id: String = type) =
        PendingAction(id = id, userId = "u", visitId = "v-$id", actionType = type, latitude = 0.0, longitude = 0.0)

    @Test
    fun logoutPolicy_countsAndNamesOutletPhotos() {
        val d = LogoutPolicy.decide(
            listOf(act("CHECK_IN", "1"), act(PendingAction.TYPE_PAYMENT_CREATE, "2"), act(PendingAction.TYPE_OUTLET_PROOF, "3"))
        )
        d as LogoutDecision.ConfirmUnsynced
        assertEquals(3, d.count)
        assertEquals("check-ins, payments, outlet photos", d.description)
        assertEquals(
            "You have 3 unsynced items (check-ins, payments, outlet photos). Sync now before logging out?",
            LogoutPolicy.logoutWarning(d.count, d.description)
        )
    }

    @Test
    fun orphanSweep_deletesOnlyOldUnreferencedFiles() {
        val dir = Files.createTempDirectory("outlet_proofs").toFile()
        try {
            val now = 10L * 24 * 3600_000
            fun file(name: String, ageDays: Long) = File(dir, name).also {
                it.writeBytes(byteArrayOf(1)); it.setLastModified(now - ageDays * 24 * 3600_000)
            }
            val oldOrphan = file("old_orphan.jpg", 8)
            val oldReferenced = file("old_ref.jpg", 8)
            val recent = file("recent.jpg", 1)
            val deleted = OutletProofStore.pruneOrphanedIn(dir, setOf(oldReferenced.absolutePath), nowMs = now)
            assertEquals(1, deleted)
            assertFalse(oldOrphan.exists())
            assertTrue(oldReferenced.exists())
            assertTrue(recent.exists())
        } finally {
            dir.deleteRecursively()
        }
    }
}
