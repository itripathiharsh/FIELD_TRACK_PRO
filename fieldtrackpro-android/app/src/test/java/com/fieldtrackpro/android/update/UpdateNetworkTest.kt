package com.fieldtrackpro.android.update

import kotlinx.coroutines.runBlocking
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.File
import java.nio.file.Files
import java.security.MessageDigest

/** Download, resume and verification against a fake HTTP layer (no real network). */
class UpdateNetworkTest {
    private val payload = ByteArray(300_000) { (it % 251).toByte() }
    private val sha = MessageDigest.getInstance("SHA-256").digest(payload).joinToString("") { "%02x".format(it) }
    private val dir: File = Files.createTempDirectory("ftupd").toFile()
    private val ranges = mutableListOf<String?>()

    private fun network(supportRange: Boolean = true, body: ByteArray = payload): UpdateNetwork {
        val fake = Interceptor { chain ->
            val req = chain.request()
            val range = req.header("Range")
            ranges += range
            val start = range?.removePrefix("bytes=")?.removeSuffix("-")?.toIntOrNull()
            val (code, bytes) = if (supportRange && start != null) 206 to body.copyOfRange(start, body.size) else 200 to body
            Response.Builder().request(req).protocol(Protocol.HTTP_1_1).code(code).message("x")
                .body(bytes.toResponseBody("application/vnd.android.package-archive".toMediaType())).build()
        }
        val client = OkHttpClient.Builder().addInterceptor(UpdateNetwork.hostGuard(HOSTS)).addInterceptor(fake).build()
        return UpdateNetwork(HOSTS, client)
    }

    private fun m(sha256: String = sha, size: Long? = payload.size.toLong()) = manifest(sha = sha256, size = size)

    @Test fun downloadsAndVerifies() = runBlocking {
        var last = 0L
        val f = network().downloadApk(m(), dir) { d, _ -> last = d }
        assertArrayEquals(payload, f.readBytes())
        assertEquals(payload.size.toLong(), last)
        assertEquals("FieldTrackPro-7.apk", f.name)
    }

    @Test fun shaMismatchDeletesTheFile() = runBlocking {
        try {
            network().downloadApk(m(sha256 = "0".repeat(64)), dir) { _, _ -> }
            fail("expected verification failure")
        } catch (e: UpdateNetwork.VerificationException) {
            assertTrue(e.message!!.contains("SHA-256"))
        }
        assertTrue(dir.listFiles()!!.isEmpty())
    }

    @Test fun sizeMismatchIsRejected() = runBlocking {
        try {
            network().downloadApk(m(size = payload.size + 1L), dir) { _, _ -> }
            fail("expected verification failure")
        } catch (e: UpdateNetwork.VerificationException) {
            assertTrue(e.message!!.contains("size"))
        }
    }

    @Test fun resumesAPartialDownload() = runBlocking {
        File(dir, "FieldTrackPro-7.part").writeBytes(payload.copyOfRange(0, 100_000))
        val f = network().downloadApk(m(), dir) { _, _ -> }
        assertEquals("bytes=100000-", ranges.single())
        assertArrayEquals(payload, f.readBytes())
    }

    @Test fun restartsWhenTheServerIgnoresRange() = runBlocking {
        File(dir, "FieldTrackPro-7.part").writeBytes(payload.copyOfRange(0, 100_000))
        val f = network(supportRange = false).downloadApk(m(), dir) { _, _ -> }
        assertArrayEquals(payload, f.readBytes())
    }

    @Test fun reusesAnAlreadyVerifiedDownload() = runBlocking {
        File(dir, "FieldTrackPro-7.apk").writeBytes(payload)
        network().downloadApk(m(), dir) { _, _ -> }
        assertTrue(ranges.isEmpty()) // no network call
    }

    @Test fun untrustedHostsAreBlocked() = runBlocking {
        try {
            network().downloadApk(manifest(url = "https://evil.example.com/x.apk", sha = sha), dir) { _, _ -> }
            fail("expected block")
        } catch (e: UpdateNetwork.UntrustedHostException) { }
        try {
            network().fetchManifest("http://fieldtrack-pro-rosy.vercel.app/downloads/app-update.json")
            fail("expected block")
        } catch (e: UpdateNetwork.UntrustedHostException) { }
        assertFalse(ranges.isNotEmpty())
    }
}
