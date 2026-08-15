package com.fieldtrackpro.android.ui.screens.media

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.MediaRepository
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.ui.components.ErrorBanner
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.theme.FieldTrackNavy
import com.fieldtrackpro.android.ui.theme.SurfaceOffWhite
import com.fieldtrackpro.android.ui.theme.SurfaceWhite
import com.fieldtrackpro.android.ui.theme.TextMuted
import com.fieldtrackpro.android.ui.theme.TextPrimary
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Request

@Composable
fun AttachmentPreviewScreen(
    mediaId: String,
    fileName: String,
    isPhoto: Boolean,
    onNavigateBack: () -> Unit
) {
    val context = LocalContext.current

    var isLoading by remember { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var bitmap by remember { mutableStateOf<android.graphics.Bitmap?>(null) }
    var mediaType by remember { mutableStateOf(if (isPhoto) "PHOTO" else "DOCUMENT") }
    var mediaFilename by remember { mutableStateOf(fileName) }
    var fileSizeBytes by remember { mutableStateOf(0L) }

    LaunchedEffect(mediaId) {
        isLoading = true
        errorMessage = null

        try {
            val tokenManager = TokenManager(context)
            val repository = MediaRepository(ApiClient.createMediaApi(tokenManager))

            when (val metaResult = repository.getMediaMetadata(mediaId)) {
                is Resource.Success -> {
                    mediaType = metaResult.data.mediaType
                    mediaFilename = metaResult.data.displayName
                    fileSizeBytes = metaResult.data.fileSizeBytes
                }
                is Resource.Error -> {
                    errorMessage = metaResult.message
                    isLoading = false
                    return@LaunchedEffect
                }
                else -> {
                    isLoading = false
                    return@LaunchedEffect
                }
            }

            when (val urlResult = repository.getMediaDownloadUrl(mediaId)) {
                is Resource.Success -> {
                    val downloadUrl = urlResult.data.download_url

                    val bytes = withContext(Dispatchers.IO) {
                        val client = ApiClient.createOkHttpClientForDownload(tokenManager)
                        val request = Request.Builder().url(downloadUrl).build()
                        val response = client.newCall(request).execute()
                        if (response.isSuccessful) {
                            response.body?.bytes()
                        } else {
                            throw Exception("Download failed: HTTP ${response.code}")
                        }
                    }

                    if (bytes == null || bytes.isEmpty()) {
                        errorMessage = "Downloaded file is empty"
                        isLoading = false
                        return@LaunchedEffect
                    }

                    if (mediaType == "PHOTO") {
                        val decoded = withContext(Dispatchers.IO) {
                            // P1-10: sampled decode, not a full-resolution
                            // one immediately scaled down for display.
                            com.fieldtrackpro.android.utils.ImageDownsampler.decodeSampledBitmapForDisplay(bytes)
                        }
                        if (decoded != null) {
                            bitmap = decoded
                        } else {
                            errorMessage = "Unable to decode image. The file may be corrupted or in an unsupported format."
                        }
                    }

                    isLoading = false
                }
                is Resource.Error -> {
                    errorMessage = urlResult.message
                    isLoading = false
                }
                else -> {
                    isLoading = false
                }
            }
        } catch (e: Exception) {
            errorMessage = "Failed to load attachment: ${e.localizedMessage ?: "Unknown error"}"
            isLoading = false
        }
    }

    Scaffold(
        topBar = {
            FieldTrackTopAppBar(
                title = mediaFilename,
                onBackClick = onNavigateBack
            )
        }
    ) { innerPadding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .background(SurfaceOffWhite),
            contentAlignment = Alignment.Center
        ) {
            when {
                isLoading -> Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    CircularProgressIndicator(color = FieldTrackNavy)
                    Text(
                        text = "Loading attachment...",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TextMuted
                    )
                }

                errorMessage != null -> Column(
                    modifier = Modifier.padding(20.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(16.dp)
                ) {
                    ErrorBanner(message = errorMessage!!)
                    Button(
                        onClick = onNavigateBack,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = FieldTrackNavy,
                            contentColor = SurfaceWhite
                        )
                    ) {
                        Text("Go Back", color = SurfaceWhite)
                    }
                }

                mediaType == "PHOTO" && bitmap != null -> {
                    Image(
                        bitmap = bitmap!!.asImageBitmap(),
                        contentDescription = mediaFilename,
                        modifier = Modifier.fillMaxSize(),
                        contentScale = ContentScale.Fit
                    )
                }

                mediaType == "DOCUMENT" -> {
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(20.dp),
                        colors = CardDefaults.cardColors(containerColor = SurfaceWhite),
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Column(modifier = Modifier.padding(24.dp)) {
                            Text(
                                text = "Document",
                                style = MaterialTheme.typography.titleLarge,
                                color = FieldTrackNavy
                            )
                            Text(
                                text = mediaFilename,
                                style = MaterialTheme.typography.bodyLarge,
                                color = TextPrimary,
                                modifier = Modifier.padding(top = 8.dp)
                            )
                            Text(
                                text = "Size: ${formatFileSize(fileSizeBytes)}",
                                style = MaterialTheme.typography.bodyMedium,
                                color = TextMuted,
                                modifier = Modifier.padding(top = 4.dp)
                            )
                            Text(
                                text = "Type: $mediaType",
                                style = MaterialTheme.typography.bodyMedium,
                                color = TextMuted,
                                modifier = Modifier.padding(top = 4.dp)
                            )
                            Text(
                                text = "Inline document preview is not available. Use the backend API to download the file.",
                                style = MaterialTheme.typography.bodySmall,
                                color = TextMuted,
                                modifier = Modifier.padding(top = 12.dp)
                            )

                            Button(
                                onClick = onNavigateBack,
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(top = 20.dp),
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = FieldTrackNavy,
                                    contentColor = SurfaceWhite
                                )
                            ) {
                                Text("Done", color = SurfaceWhite)
                            }
                        }
                    }
                }

                else -> {
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(20.dp),
                        colors = CardDefaults.cardColors(containerColor = SurfaceWhite),
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Column(modifier = Modifier.padding(24.dp)) {
                            Text(
                                text = "Preview Unavailable",
                                style = MaterialTheme.typography.titleLarge,
                                color = FieldTrackNavy
                            )
                            Text(
                                text = "This media type cannot be previewed. The file may be missing from storage or in an unsupported format.",
                                style = MaterialTheme.typography.bodyMedium,
                                color = TextMuted,
                                modifier = Modifier.padding(top = 8.dp)
                            )
                            Button(
                                onClick = onNavigateBack,
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(top = 16.dp),
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = FieldTrackNavy,
                                    contentColor = SurfaceWhite
                                )
                            ) {
                                Text("Go Back", color = SurfaceWhite)
                            }
                        }
                    }
                }
            }
        }
    }
}

private fun formatFileSize(bytes: Long): String {
    return when {
        bytes < 1024 -> "$bytes B"
        bytes < 1024 * 1024 -> "${bytes / 1024} KB"
        else -> String.format("%.1f MB", bytes / (1024.0 * 1024.0))
    }
}
