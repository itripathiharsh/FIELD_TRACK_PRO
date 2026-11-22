package com.fieldtrackpro.android.ui.components

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import android.util.LruCache
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.MediaRepository
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.TextSecondary
import com.fieldtrackpro.android.utils.ImageDownsampler
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Request
import java.io.File

/** Kind of an attachment, decided from what the backend tells us (never from a private URL). */
enum class AttachmentKind {
    IMAGE, PDF, OTHER;

    companion object {
        fun of(fileName: String?, isPhoto: Boolean): AttachmentKind {
            val n = fileName?.lowercase().orEmpty()
            return when {
                isPhoto || n.endsWith(".jpg") || n.endsWith(".jpeg") || n.endsWith(".png") || n.endsWith(".webp") -> IMAGE
                n.endsWith(".pdf") -> PDF
                else -> OTHER
            }
        }
    }
}

/** Small in-memory cache of thumbnails (bounded to ~8 MB) so scrolling does not re-download. */
private object ThumbCache {
    private val cache = object : LruCache<String, Bitmap>(8 * 1024 * 1024) {
        override fun sizeOf(key: String, value: Bitmap) = value.byteCount
    }

    fun get(id: String): Bitmap? = cache.get(id)
    fun put(id: String, b: Bitmap) {
        cache.put(id, b)
    }
}

/** Downloads an authenticated attachment and decodes a small preview. The download URL is never logged or shown. */
private suspend fun loadThumb(context: Context, mediaId: String, kind: AttachmentKind, px: Int): Result<Bitmap> =
    withContext(Dispatchers.IO) {
        runCatching {
            val tm = TokenManager.getInstance(context)
            val repo = MediaRepository(ApiClient.createMediaApi(tm))
            val url = (repo.getMediaDownloadUrl(mediaId) as? Resource.Success)?.data?.download_url
                ?: error("This file is not available right now.")
            val response = ApiClient.createOkHttpClientForDownload(tm).newCall(Request.Builder().url(url).build()).execute()
            response.use { r ->
                if (!r.isSuccessful) error("The file could not be downloaded (${r.code}).")
                val body = r.body ?: error("The file is empty.")
                if (body.contentLength() > 25L * 1024 * 1024) error("The file is too large to preview.")
                val bytes = body.bytes()
                val bmp = when (kind) {
                    AttachmentKind.PDF -> renderPdfFirstPage(context, bytes, px)
                    else -> ImageDownsampler.decodeSampledBitmapForDisplay(bytes, px)
                }
                bmp ?: error("The file could not be shown. It may be damaged.")
            }
        }
    }

private fun renderPdfFirstPage(context: Context, bytes: ByteArray, px: Int): Bitmap? {
    val tmp = File.createTempFile("pdfthumb_", ".pdf", context.cacheDir)
    return try {
        tmp.writeBytes(bytes)
        ParcelFileDescriptor.open(tmp, ParcelFileDescriptor.MODE_READ_ONLY).use { fd ->
            PdfRenderer(fd).use { pr ->
                if (pr.pageCount == 0) return null
                pr.openPage(0).use { page ->
                    val scale = px.toFloat() / maxOf(page.width, page.height)
                    val bmp = Bitmap.createBitmap(
                        (page.width * scale).toInt().coerceAtLeast(1),
                        (page.height * scale).toInt().coerceAtLeast(1),
                        Bitmap.Config.ARGB_8888
                    )
                    bmp.eraseColor(Color.WHITE)
                    page.render(bmp, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                    bmp
                }
            }
        }
    } catch (e: Exception) {
        null
    } finally {
        tmp.delete() // the temporary copy is removed immediately
    }
}

/**
 * Reusable thumbnail for an attachment already stored on the server: image preview, PDF first page,
 * or a file icon. Shows a spinner while loading and a tap-to-retry state if the download fails.
 */
@Composable
fun AttachmentThumbnail(
    mediaId: String,
    fileName: String?,
    isPhoto: Boolean,
    modifier: Modifier = Modifier,
    size: Dp = 64.dp,
) {
    val context = LocalContext.current
    val kind = remember(fileName, isPhoto) { AttachmentKind.of(fileName, isPhoto) }
    var bitmap by remember(mediaId) { mutableStateOf(ThumbCache.get(mediaId)) }
    var failed by remember(mediaId) { mutableStateOf(false) }
    var attempt by remember(mediaId) { mutableIntStateOf(0) }
    val px = with(LocalDensity.current) { size.roundToPx() * 2 }

    LaunchedEffect(mediaId, attempt) {
        if (kind == AttachmentKind.OTHER || bitmap != null) return@LaunchedEffect
        failed = false
        loadThumb(context, mediaId, kind, px)
            .onSuccess { ThumbCache.put(mediaId, it); bitmap = it }
            .onFailure { failed = true }
    }

    Box(
        modifier = modifier
            .size(size)
            .clip(RoundedCornerShape(10.dp))
            .background(androidx.compose.ui.graphics.Color(0xFFF1F3F6))
            .let { if (failed) it.clickable { attempt++ } else it },
        contentAlignment = Alignment.Center
    ) {
        val b = bitmap
        when {
            b != null -> Image(b.asImageBitmap(), contentDescription = fileName, contentScale = ContentScale.Crop, modifier = Modifier.size(size))
            failed -> Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Icon(Icons.Default.Refresh, contentDescription = "Tap to retry", tint = TextSecondary, modifier = Modifier.size(22.dp))
                Text("Retry", fontSize = 10.sp, color = TextSecondary)
            }
            kind == AttachmentKind.OTHER -> Icon(Icons.Default.Description, contentDescription = null, tint = BrandNavy, modifier = Modifier.size(28.dp))
            else -> CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp, color = BrandNavy)
        }
    }
}
