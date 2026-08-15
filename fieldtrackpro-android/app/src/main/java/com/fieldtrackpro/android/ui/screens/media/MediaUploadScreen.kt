package com.fieldtrackpro.android.ui.screens.media

import android.Manifest
import android.content.pm.PackageManager
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import com.fieldtrackpro.android.ui.components.EmptyState
import com.fieldtrackpro.android.ui.components.ErrorBanner
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.components.StatusBadge
import com.fieldtrackpro.android.ui.theme.FieldTrackAmber
import com.fieldtrackpro.android.ui.theme.FieldTrackNavy
import com.fieldtrackpro.android.ui.theme.SurfaceOffWhite
import com.fieldtrackpro.android.ui.theme.SurfaceWhite
import com.fieldtrackpro.android.ui.theme.TextMuted
import com.fieldtrackpro.android.ui.theme.TextPrimary
import com.fieldtrackpro.android.ui.viewmodel.MediaState
import com.fieldtrackpro.android.ui.viewmodel.MediaViewModel
import com.fieldtrackpro.android.utils.ImageDownsampler
import java.io.File

@Composable
fun MediaUploadScreen(
    visitId: String,
    viewModel: MediaViewModel,
    onNavigateBack: () -> Unit,
    onPreviewMedia: (mediaId: String, fileName: String, isPhoto: Boolean) -> Unit = { _, _, _ -> },
    // P2-B: order capture reuses this exact screen/upload pipeline - the
    // caller (VisitDetailsScreen's "Capture Order" entry point) is the only
    // thing that differs, per "don't create a second camera implementation".
    isOrderMode: Boolean = false
) {
    val context = LocalContext.current
    val state by viewModel.mediaState.collectAsState()

    var cameraUri by remember { mutableStateOf<Uri?>(null) }
    var capturedPreviewUri by remember { mutableStateOf<Uri?>(null) }
    var orderNote by remember { mutableStateOf("") }

    fun dispatchUpload(uri: Uri, mimeType: String) {
        if (isOrderMode) {
            uploadOrder(context, viewModel, visitId, uri, mimeType, orderNote.ifBlank { null })
        } else {
            uploadFile(context, viewModel, visitId, uri, mimeType)
        }
    }
    var hasCameraPermission by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) ==
                PackageManager.PERMISSION_GRANTED
        )
    }
    var hasCameraFeature by remember {
        mutableStateOf(context.packageManager.hasSystemFeature(PackageManager.FEATURE_CAMERA_ANY))
    }

    val cameraLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.TakePicture()
    ) { success ->
        if (success && cameraUri != null) {
            capturedPreviewUri = cameraUri
        }
    }

    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { granted ->
        hasCameraPermission = granted
        if (granted) {
            val uri = createTempImageUri(context)
            cameraUri = uri
            cameraLauncher.launch(uri)
        }
    }

    val imagePickerLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.GetContent()
    ) { uri ->
        if (uri != null) {
            val mimeType = context.contentResolver.getType(uri) ?: "image/*"
            dispatchUpload(uri, mimeType)
        }
    }

    val documentPickerLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.GetContent()
    ) { uri ->
        if (uri != null) {
            val mimeType = context.contentResolver.getType(uri) ?: "application/pdf"
            uploadFile(context, viewModel, visitId, uri, mimeType)
        }
    }

    LaunchedEffect(visitId) {
        viewModel.loadVisitMedia(visitId)
    }

    Scaffold(
        topBar = {
            FieldTrackTopAppBar(
                title = if (isOrderMode) "Capture Order" else "Visit Media & Attachments",
                onBackClick = onNavigateBack
            )
        }
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(SurfaceOffWhite)
                .padding(innerPadding)
                .padding(20.dp)
        ) {
            // Camera Preview Section
            if (capturedPreviewUri != null) {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
                ) {
                    Column(modifier = Modifier.padding(20.dp)) {
                        Text(
                            text = "Photo Preview",
                            style = MaterialTheme.typography.titleLarge,
                            color = FieldTrackNavy
                        )
                        Text(
                            text = "Review your photo before uploading.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = TextMuted
                        )

                        Spacer(modifier = Modifier.height(12.dp))

                        Card(
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(200.dp),
                            colors = CardDefaults.cardColors(containerColor = SurfaceOffWhite)
                        ) {
                            Column(
                                modifier = Modifier.fillMaxSize(),
                                horizontalAlignment = Alignment.CenterHorizontally,
                                verticalArrangement = Arrangement.Center
                            ) {
                                Text(
                                    text = "Photo captured successfully",
                                    fontSize = 14.sp,
                                    color = TextPrimary,
                                    fontWeight = FontWeight.Bold
                                )
                                Text(
                                    text = "Tap Upload to attach to visit",
                                    fontSize = 12.sp,
                                    color = TextMuted
                                )
                            }
                        }

                        Spacer(modifier = Modifier.height(12.dp))

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            OutlinedButton(
                                onClick = {
                                    capturedPreviewUri = null
                                    cameraUri = null
                                },
                                modifier = Modifier.weight(1f),
                                enabled = (state !is MediaState.Loading)
                            ) {
                                Text("Retake", fontSize = 12.sp, color = FieldTrackNavy)
                            }

                            Button(
                                onClick = {
                                    val uri = capturedPreviewUri
                                    if (uri != null) {
                                        dispatchUpload(uri, "image/jpeg")
                                        capturedPreviewUri = null
                                        cameraUri = null
                                    }
                                },
                                modifier = Modifier.weight(1f),
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = FieldTrackNavy,
                                    contentColor = SurfaceWhite
                                ),
                                enabled = (state !is MediaState.Loading)
                            ) {
                                Text("Upload", fontSize = 12.sp, color = SurfaceWhite)
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(24.dp))
            }

            // Upload Controls
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
            ) {
                Column(modifier = Modifier.padding(20.dp)) {
                    Text(
                        text = if (isOrderMode) "Capture Order" else "Upload Attachment",
                        style = MaterialTheme.typography.titleLarge,
                        color = FieldTrackNavy
                    )
                    Text(
                        text = if (isOrderMode)
                            "Photograph the order and add a short diary note."
                        else
                            "Upload site photos or documents (JPEG, PNG, PDF supported up to 10MB).",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TextMuted
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    if (isOrderMode) {
                        OutlinedTextField(
                            value = orderNote,
                            onValueChange = { orderNote = it },
                            label = { Text("Order note (e.g. 5x Usha fans, 2x Singer mixers)") },
                            modifier = Modifier.fillMaxWidth(),
                            minLines = 2
                        )
                        Spacer(modifier = Modifier.height(16.dp))
                    }

                    if (state is MediaState.Error) {
                        ErrorBanner(message = (state as MediaState.Error).message)
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    // P1-6: a transient failure was queued for automatic
                    // background retry - tell the rep their photo is not
                    // lost, distinct from a permanent Error.
                    if (state is MediaState.QueuedForRetry) {
                        Text(
                            text = "Queued for automatic retry - will upload once connection improves.",
                            fontSize = 13.sp,
                            color = FieldTrackAmber,
                            fontWeight = FontWeight.Bold
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    if (state is MediaState.UploadSuccess) {
                        Text(
                            text = "Upload successful!",
                            fontSize = 13.sp,
                            color = FieldTrackNavy,
                            fontWeight = FontWeight.Bold
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Button(
                            onClick = {
                                if (hasCameraFeature) {
                                    if (hasCameraPermission) {
                                        val uri = createTempImageUri(context)
                                        cameraUri = uri
                                        cameraLauncher.launch(uri)
                                    } else {
                                        permissionLauncher.launch(Manifest.permission.CAMERA)
                                    }
                                }
                            },
                            modifier = Modifier.weight(1f),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = if (hasCameraFeature) FieldTrackNavy else TextMuted,
                                contentColor = SurfaceWhite
                            ),
                            enabled = ((state !is MediaState.Loading)) && hasCameraFeature
                        ) {
                            Text("Camera", fontSize = 12.sp, color = SurfaceWhite)
                        }

                        OutlinedButton(
                            onClick = { imagePickerLauncher.launch("image/*") },
                            modifier = Modifier.weight(1f),
                            enabled = (state !is MediaState.Loading)
                        ) {
                            Text("Photo", fontSize = 12.sp, color = FieldTrackNavy)
                        }

                        // Orders are always a photographed diary note - no
                        // document upload path in this mode.
                        if (!isOrderMode) {
                            OutlinedButton(
                                onClick = { documentPickerLauncher.launch("application/pdf") },
                                modifier = Modifier.weight(1f),
                                enabled = (state !is MediaState.Loading)
                            ) {
                                Text("PDF", fontSize = 12.sp, color = FieldTrackNavy)
                            }
                        }
                    }

                    if (state is MediaState.Loading) {
                        Spacer(modifier = Modifier.height(12.dp))
                        CircularProgressIndicator(
                            modifier = Modifier.align(Alignment.CenterHorizontally),
                            color = FieldTrackNavy
                        )
                    }

                    if (hasCameraFeature.not()) {
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = "Camera not available on this device",
                            fontSize = 11.sp,
                            color = TextMuted
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            // Existing Attachments Section
            Text(
                text = "Existing Attachments",
                style = MaterialTheme.typography.titleMedium,
                color = FieldTrackNavy
            )

            Spacer(modifier = Modifier.height(12.dp))

            when (val s = state) {
                is MediaState.ListSuccess -> {
                    // Orders and generic attachments are shown in their own
                    // screen instance (matches web's split between "Attached
                    // Media" and "Orders" sections on the same visit).
                    val items = s.items.filter { it.isOrder == isOrderMode }
                    if (items.isEmpty()) {
                        EmptyState(
                            title = if (isOrderMode) "No Orders" else "No Attachments",
                            subtitle = if (isOrderMode) "No orders captured for this visit yet." else "No files uploaded for this visit yet."
                        )
                    } else {
                        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            items(items) { media ->
                                Card(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .clickable {
                                            onPreviewMedia(
                                                media.id,
                                                media.displayName,
                                                media.isPhoto
                                            )
                                        },
                                    shape = RoundedCornerShape(12.dp),
                                    colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
                                ) {
                                    Row(
                                        modifier = Modifier
                                            .padding(14.dp)
                                            .fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Column {
                                            Text(
                                                text = media.originalFilename ?: media.storageKey.split("/").lastOrNull() ?: media.id,
                                                fontSize = 14.sp,
                                                fontWeight = FontWeight.Bold,
                                                color = TextPrimary
                                            )
                                            Text(
                                                text = "Size: ${media.fileSizeBytes} bytes | Type: ${media.mediaType}",
                                                fontSize = 12.sp,
                                                color = TextMuted
                                            )
                                            if (!media.note.isNullOrBlank()) {
                                                Text(
                                                    text = media.note,
                                                    fontSize = 12.sp,
                                                    color = TextPrimary
                                                )
                                            }
                                        }
                                        StatusBadge(status = media.mediaType)
                                    }
                                }
                            }
                        }
                    }
                }
                else -> {}
            }
        }
    }
}

private fun createTempImageUri(context: android.content.Context): Uri {
    val tempFile = File.createTempFile(
        "capture_${System.currentTimeMillis()}",
        ".jpg",
        context.cacheDir
    )
    return FileProvider.getUriForFile(
        context,
        "${context.packageName}.fileprovider",
        tempFile
    )
}

/**
 * P1-10: for an image, downsample/compress before upload rather than reading
 * the picker/camera Uri's full-resolution bytes as-is - see ImageDownsampler
 * for the chosen limits and why. A document (e.g. PDF) is passed through
 * unchanged; it isn't an image and can't be downsampled this way.
 */
private fun readBytesForUpload(context: android.content.Context, uri: Uri, mimeType: String): Pair<ByteArray, String>? {
    if (mimeType.startsWith("image/")) {
        ImageDownsampler.downsample(context, uri)?.let { return it to "image/jpeg" }
        // Decoding as an image failed - fall through to the raw-bytes path
        // below rather than blocking the upload outright.
    }
    val inputStream = context.contentResolver.openInputStream(uri)
    val bytes = inputStream?.readBytes()
    inputStream?.close()
    return bytes?.takeIf { it.isNotEmpty() }?.let { it to mimeType }
}

private fun uploadFile(
    context: android.content.Context,
    viewModel: MediaViewModel,
    visitId: String,
    uri: Uri,
    mimeType: String
) {
    try {
        val (bytes, resolvedMimeType) = readBytesForUpload(context, uri, mimeType)
            ?: return viewModel.reportError("Could not read the selected file.")
        val fileName = uri.lastPathSegment ?: "attachment_${System.currentTimeMillis()}"
        viewModel.uploadMedia(visitId, fileName, resolvedMimeType, bytes)
    } catch (e: Exception) {
        viewModel.reportError(e.localizedMessage ?: "Could not read the selected file.")
    }
}

/** P2-B: order capture - identical to uploadFile, routed through captureOrder instead. */
private fun uploadOrder(
    context: android.content.Context,
    viewModel: MediaViewModel,
    visitId: String,
    uri: Uri,
    mimeType: String,
    note: String?
) {
    try {
        val (bytes, resolvedMimeType) = readBytesForUpload(context, uri, mimeType)
            ?: return viewModel.reportError("Could not read the selected file.")
        val fileName = uri.lastPathSegment ?: "order_${System.currentTimeMillis()}"
        viewModel.captureOrder(visitId, fileName, resolvedMimeType, bytes, note)
    } catch (e: Exception) {
        viewModel.reportError(e.localizedMessage ?: "Could not read the selected file.")
    }
}
