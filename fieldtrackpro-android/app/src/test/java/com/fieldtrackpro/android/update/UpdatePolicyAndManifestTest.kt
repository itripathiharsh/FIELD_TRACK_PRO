package com.fieldtrackpro.android.update

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

internal const val PKG = "com.fieldtrackpro.android"
internal val HOSTS = setOf("fieldtrack-pro-rosy.vercel.app")
internal const val SHA = "f8b71a4ba5d8c284b50d57f46222cbbdb7b3262c9af1dc2050ecb4094ca892c7"

internal fun manifest(
    code: Long = 7,
    mandatory: Boolean = false,
    min: Long = 0,
    url: String = "https://fieldtrack-pro-rosy.vercel.app/downloads/releases/FieldTrackPro-1.3.1-7.apk",
    sha: String? = SHA,
    pkg: String = PKG,
    size: Long? = 1000
) = UpdateManifest(1, pkg, code, "1.3.$code", url, sha, size, min, mandatory, listOf("Faster dashboard"), "2026-11-22")

class UpdateManifestTest {
    @Test fun parsesThePublishedFormat() {
        val m = UpdateManifest.parse(
            """{"schema":1,"packageName":"$PKG","versionCode":7,"versionName":"1.3.1",
               "apkUrl":"https://fieldtrack-pro-rosy.vercel.app/downloads/releases/a.apk","apkSha256":"$SHA",
               "apkSizeBytes":1000,"minSupportedVersionCode":6,"mandatory":true,"releaseNotes":["A","B"]}"""
        )!!
        assertEquals(7L, m.versionCode)
        assertTrue(m.mandatory)
        assertEquals(listOf("A", "B"), m.releaseNotes)
        assertNull(m.problem(PKG, HOSTS))
        assertNull(UpdateManifest.parse("not json"))
    }

    @Test fun rejectsUntrustedOrMalformedManifests() {
        assertNotNull(manifest(url = "http://fieldtrack-pro-rosy.vercel.app/x.apk").problem(PKG, HOSTS))   // not https
        assertNotNull(manifest(url = "https://evil.example.com/x.apk").problem(PKG, HOSTS))               // other host
        assertNotNull(manifest(url = "https://fieldtrack-pro-rosy.vercel.app.evil.com/x.apk").problem(PKG, HOSTS))
        assertNotNull(manifest(url = "https://user@fieldtrack-pro-rosy.vercel.app/x.apk").problem(PKG, HOSTS))
        assertNotNull(manifest(sha = null).problem(PKG, HOSTS))
        assertNotNull(manifest(sha = "abc").problem(PKG, HOSTS))
        assertNotNull(manifest(pkg = "com.other.app").problem(PKG, HOSTS))
        assertNotNull(manifest(code = 7, min = 8).problem(PKG, HOSTS))
        assertNotNull(manifest(size = 0).problem(PKG, HOSTS))
        assertNotNull(manifest().copy(schema = 2).problem(PKG, HOSTS))
    }
}

class UpdatePolicyTest {
    private val none = UpdatePolicy.SnoozeState()
    private fun decide(installed: Long, m: UpdateManifest?, snooze: UpdatePolicy.SnoozeState = none, now: Long = 1_000_000) =
        UpdatePolicy.decide(installed, m, PKG, HOSTS, snooze, now)

    @Test fun neverOffersADowngradeOrTheSameVersion() {
        assertEquals(UpdatePolicy.Decision.UpToDate, decide(7, manifest(code = 7)))
        assertEquals(UpdatePolicy.Decision.UpToDate, decide(9, manifest(code = 7, mandatory = true)))
    }

    @Test fun optionalAndMandatory() {
        assertTrue(decide(6, manifest()) is UpdatePolicy.Decision.Optional)
        assertTrue(decide(6, manifest(mandatory = true)) is UpdatePolicy.Decision.Mandatory)
        // Below the minimum supported version => mandatory even if the flag is false.
        val below = decide(5, manifest(min = 6))
        assertTrue(below is UpdatePolicy.Decision.Mandatory)
        assertTrue((below as UpdatePolicy.Decision.Mandatory).reason.contains("no longer supported"))
    }

    @Test fun invalidManifestIsIgnored() {
        assertTrue(decide(6, manifest(url = "https://evil.example.com/x.apk")) is UpdatePolicy.Decision.Ignored)
        assertTrue(decide(6, null) is UpdatePolicy.Decision.Ignored)
    }

    @Test fun laterSnoozesOnlyThatVersionAndNeverAMandatoryOne() {
        val now = 1_000_000L
        val s = UpdatePolicy.snoozeAfterLater(none, 7, now)
        assertTrue(decide(6, manifest(code = 7), s, now + 1) is UpdatePolicy.Decision.Snoozed)
        assertTrue(decide(6, manifest(code = 7), s, now + UpdatePolicy.SNOOZE_MS) is UpdatePolicy.Decision.Optional)
        assertTrue(decide(6, manifest(code = 8), s, now + 1) is UpdatePolicy.Decision.Optional)     // newer version
        assertTrue(decide(6, manifest(code = 7, mandatory = true), s, now + 1) is UpdatePolicy.Decision.Mandatory)
    }

    @Test fun repeatedLaterStretchesTheReminder() {
        var s = UpdatePolicy.SnoozeState()
        repeat(2) { s = UpdatePolicy.snoozeAfterLater(s, 7, 0) }
        assertEquals(UpdatePolicy.SNOOZE_MS, s.untilMs)
        s = UpdatePolicy.snoozeAfterLater(s, 7, 0)
        assertEquals(3, s.count)
        assertEquals(UpdatePolicy.LONG_SNOOZE_MS, s.untilMs)
        assertEquals(1, UpdatePolicy.snoozeAfterLater(s, 8, 0).count) // counter resets for a new version
    }

    @Test fun checkFrequency() {
        assertTrue(UpdatePolicy.shouldCheckNow(lastCheckMs = 100, nowMs = 200, coldStart = true))
        assertFalse(UpdatePolicy.shouldCheckNow(lastCheckMs = 100, nowMs = 200, coldStart = false))
        assertTrue(UpdatePolicy.shouldCheckNow(lastCheckMs = 100, nowMs = 100 + UpdatePolicy.MIN_CHECK_INTERVAL_MS, coldStart = false))
        assertTrue(UpdatePolicy.shouldCheckNow(lastCheckMs = 5_000, nowMs = 1_000, coldStart = false)) // clock moved back
    }
}

class ApkVerifierCompareTest {
    private val cert = setOf("aa")
    private fun cmp(pkg: String? = PKG, code: Long? = 7, certs: Set<String> = cert, installed: Long = 6, history: Set<String> = emptySet()) =
        ApkVerifier.compare(PKG, installed, 7, cert, pkg, code, certs, history)

    @Test fun acceptsTheGenuineNewerBuild() = assertEquals(ApkVerifier.Result.Ok, cmp())

    @Test fun rejectsTamperedWrongOrOlderPackages() {
        assertTrue(cmp(certs = setOf("bb")) is ApkVerifier.Result.Rejected)       // signed by someone else
        assertTrue(cmp(pkg = "com.evil") is ApkVerifier.Result.Rejected)
        assertTrue(cmp(code = 8) is ApkVerifier.Result.Rejected)                  // not the advertised version
        assertTrue(cmp(installed = 7) is ApkVerifier.Result.Rejected)             // not newer
        assertTrue(cmp(pkg = null, code = null) is ApkVerifier.Result.Rejected)   // not an APK
        assertTrue(cmp(certs = emptySet()) is ApkVerifier.Result.Rejected)
    }

    @Test fun acceptsAnOfficialKeyRotation() {
        assertEquals(ApkVerifier.Result.Ok, cmp(certs = setOf("cc"), history = setOf("aa", "cc")))
    }
}
