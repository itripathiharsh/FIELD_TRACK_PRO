package com.fieldtrackpro.android.update

import kotlinx.coroutines.runBlocking
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import okio.buffer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import java.io.IOException
import java.nio.file.Files

/**
 * Release check (opt-in): runs the app's real manifest validation and download/resume/SHA-256 code against the
 * signed release APK and the generated app-update.json, serving the bytes locally (no network, nothing published).
 *
 *   ./gradlew testDebugUnitTest --tests "*ReleaseArtifactVerificationTest*" \
 *       -PreleaseManifest=<path>/app-update.json -PreleaseApk=<path>/FieldTrackPro-<v>-<code>.apk
 */
class ReleaseArtifactVerificationTest {
    private val manifestPath = System.getProperty("releaseManifest").orEmpty()
    private val apkPath = System.getProperty("releaseApk").orEmpty()

    @Test fun releaseManifestAndApkPassTheAppsOwnChecks() = runBlocking {
        assumeTrue(manifestPath.isNotBlank() && apkPath.isNotBlank())
        val manifest = UpdateManifest.parse(File(manifestPath).readText())!!
        val bytes = File(apkPath).readBytes()

        // Manifest is what the production app accepts.
        assertNull(manifest.problem("com.fieldtrackpro.android", setOf("fieldtrack-pro-rosy.vercel.app")))
        assertEquals(bytes.size.toLong(), manifest.apkSizeBytes)
        assertTrue(manifest.apkUrl!!.endsWith("/releases/" + File(apkPath).name))

        // Download with one interruption half-way, then resume via Range, then SHA-256 verification.
        var interruptOnce = true
        val ranges = mutableListOf<String?>()
        val server = Interceptor { chain ->
            val req = chain.request()
            ranges += req.header("Range")
            val start = req.header("Range")?.removePrefix("bytes=")?.removeSuffix("-")?.toInt() ?: 0
            val body = if (interruptOnce) {
                interruptOnce = false
                // Simulate the connection dropping after half the file.
                object : okhttp3.ResponseBody() {
                    override fun contentType() = "application/vnd.android.package-archive".toMediaType()
                    override fun contentLength() = bytes.size.toLong()
                    override fun source(): okio.BufferedSource {
                        val half = okio.Buffer().write(bytes, 0, bytes.size / 2)
                        val dropping = object : okio.Source {
                            override fun read(sink: okio.Buffer, byteCount: Long): Long {
                                val n = half.read(sink, byteCount)
                                if (n == -1L) throw IOException("connection reset")
                                return n
                            }
                            override fun timeout() = okio.Timeout.NONE
                            override fun close() {}
                        }
                        return dropping.buffer()
                    }
                }
            } else {
                bytes.copyOfRange(start, bytes.size).toResponseBody("application/vnd.android.package-archive".toMediaType())
            }
            Response.Builder().request(req).protocol(Protocol.HTTP_1_1).code(if (start > 0) 206 else 200).message("x").body(body).build()
        }
        val hosts = setOf("fieldtrack-pro-rosy.vercel.app")
        val net = UpdateNetwork(hosts, OkHttpClient.Builder().addInterceptor(UpdateNetwork.hostGuard(hosts)).addInterceptor(server).build())
        val dir = Files.createTempDirectory("ftrelease").toFile()

        val first = runCatching { net.downloadApk(manifest, dir) { _, _ -> } }
        assertTrue("first attempt must fail on the dropped connection", first.isFailure)
        val partial = File(dir, "FieldTrackPro-${manifest.versionCode}.part").length()
        assertTrue(partial > 0 && partial < bytes.size)

        val file = net.downloadApk(manifest, dir) { _, _ -> }
        assertEquals("bytes=$partial-", ranges.last())
        assertEquals(manifest.apkSha256, UpdateNetwork.sha256(file))
        println("Release artifact verified: ${file.length()} bytes, resumed at $partial, sha256 ${manifest.apkSha256}")
    }
}
