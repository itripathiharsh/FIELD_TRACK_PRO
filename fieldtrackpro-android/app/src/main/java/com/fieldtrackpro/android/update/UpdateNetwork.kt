package com.fieldtrackpro.android.update

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.io.IOException
import java.security.MessageDigest
import java.util.concurrent.TimeUnit

/**
 * Update traffic uses its OWN OkHttp client: it never carries the FieldTrack bearer token (the APK host is a static
 * site, not our API), and a network interceptor refuses every hop - including redirects - that is not https to an
 * allowed host.
 */
class UpdateNetwork(
    private val allowedHosts: Set<String>,
    client: OkHttpClient? = null
) {
    private val http: OkHttpClient = client ?: OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .addNetworkInterceptor(hostGuard(allowedHosts))
        .build()

    class UntrustedHostException(message: String) : IOException(message)
    class VerificationException(message: String) : IOException(message)

    /** Downloads the manifest text (no cache). */
    suspend fun fetchManifest(url: String): String = withContext(Dispatchers.IO) {
        if (!UpdateManifest.isTrustedUrl(url, allowedHosts)) throw UntrustedHostException("Manifest URL is not allowed")
        val request = Request.Builder().url(url).header("Cache-Control", "no-cache").build()
        http.newCall(request).execute().use { resp ->
            if (!resp.isSuccessful) throw IOException("Update check failed (HTTP ${resp.code})")
            val body = resp.body ?: throw IOException("Empty manifest")
            if (body.contentLength() > MAX_MANIFEST_BYTES) throw IOException("Manifest too large")
            val text = body.string()
            if (text.length > MAX_MANIFEST_BYTES) throw IOException("Manifest too large")
            text
        }
    }

    /**
     * Downloads [manifest]'s APK into [dir], resuming a partial file when the server supports Range requests, then
     * verifies size and SHA-256. Returns the verified file. A file that fails verification is deleted.
     */
    suspend fun downloadApk(
        manifest: UpdateManifest,
        dir: File,
        onProgress: (downloaded: Long, total: Long?) -> Unit
    ): File = withContext(Dispatchers.IO) {
        val url = manifest.apkUrl
        if (!UpdateManifest.isTrustedUrl(url, allowedHosts)) throw UntrustedHostException("APK URL is not allowed")
        dir.mkdirs()
        // Old downloads for other versions are removed so the cache does not grow.
        dir.listFiles()?.filter { !it.name.startsWith("FieldTrackPro-${manifest.versionCode}.") }?.forEach { it.delete() }

        val finalFile = File(dir, "FieldTrackPro-${manifest.versionCode}.apk")
        val partFile = File(dir, "FieldTrackPro-${manifest.versionCode}.part")
        val expectedSha = manifest.apkSha256!!.lowercase()

        // Already downloaded and verified earlier (e.g. the installer was cancelled): reuse it.
        if (finalFile.exists() && sha256(finalFile) == expectedSha) {
            onProgress(finalFile.length(), finalFile.length())
            return@withContext finalFile
        }
        finalFile.delete()

        val already = if (partFile.exists()) partFile.length() else 0L
        val builder = Request.Builder().url(url!!)
        if (already > 0) builder.header("Range", "bytes=$already-")
        http.newCall(builder.build()).execute().use { resp ->
            val append = resp.code == 206 && already > 0
            if (!resp.isSuccessful) throw IOException("Download failed (HTTP ${resp.code})")
            val body = resp.body ?: throw IOException("Empty download")
            val start = if (append) already else 0L
            val total = manifest.apkSizeBytes ?: body.contentLength().takeIf { it > 0 }?.plus(start)
            if (total != null && total > MAX_APK_BYTES) throw VerificationException("APK is larger than allowed")
            FileOutputStream(partFile, append).use { out ->
                body.byteStream().use { input ->
                    val buf = ByteArray(64 * 1024)
                    var done = start
                    var lastReported = -1L
                    while (true) {
                        currentCoroutineContext().ensureActive()
                        val n = input.read(buf)
                        if (n < 0) break
                        out.write(buf, 0, n)
                        done += n
                        if (done > MAX_APK_BYTES) throw VerificationException("APK is larger than allowed")
                        if (done - lastReported >= 128 * 1024 || done == total) {
                            onProgress(done, total)
                            lastReported = done
                        }
                    }
                    onProgress(done, total)
                }
            }
        }

        // Verify before the file is ever handed to the installer.
        manifest.apkSizeBytes?.let { size ->
            if (partFile.length() != size) {
                partFile.delete()
                throw VerificationException("Downloaded file size does not match the release (got ${partFile.length()}, expected $size)")
            }
        }
        val actual = sha256(partFile)
        if (actual != expectedSha) {
            partFile.delete()
            throw VerificationException("Downloaded file failed the SHA-256 check")
        }
        if (!partFile.renameTo(finalFile)) throw IOException("Could not store the downloaded update")
        finalFile
    }

    companion object {
        const val MAX_MANIFEST_BYTES = 64 * 1024L
        const val MAX_APK_BYTES = 250L * 1024 * 1024

        fun sha256(file: File): String {
            val md = MessageDigest.getInstance("SHA-256")
            FileInputStream(file).use { input ->
                val buf = ByteArray(64 * 1024)
                while (true) {
                    val n = input.read(buf)
                    if (n < 0) break
                    md.update(buf, 0, n)
                }
            }
            return md.digest().joinToString("") { "%02x".format(it) }
        }

        fun hostGuard(allowedHosts: Set<String>) = Interceptor { chain ->
            val url = chain.request().url
            if (!url.isHttps || allowedHosts.none { it.equals(url.host, ignoreCase = true) }) {
                throw UntrustedHostException("Blocked update request to ${url.scheme}://${url.host}")
            }
            chain.proceed(chain.request())
        }
    }
}
