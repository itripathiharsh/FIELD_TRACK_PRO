package com.fieldtrackpro.android.ui.screens.media

import android.Manifest
import android.content.pm.PackageManager
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
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
    var fieldError by remember { mutableStateOf<String?>(null) }

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
                .background(com.fieldtrackpro.android.ui.theme.SurfaceSecondary)
                .padding(innerPadding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState())
        ) {
            // Camera Preview Section
            if (capturedPreviewUri != null) {
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .border(1.dp, com.fieldtrackpro.android.ui.theme.BrandLightGray, RoundedCornerShape(14.dp)),
                    shape = RoundedCornerShape(14.dp),
                    colors = CardDefaults.cardColors(containerColor = com.fieldtrackpro.android.ui.theme.BrandWhite),
                    elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
                ) {
                    Column(modifier = Modifier.padding(18.dp)) {
                        Text(
                            text = "Photo Preview",
                            fontFamily = com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily,
                            fontSize = 18.sp,
                            fontWeight = FontWeight.Bold,
                            color = com.fieldtrackpro.android.ui.theme.BrandNavy
                        )
                        Text(
                            text = "Review your photo before uploading.",
                            fontFamily = com.fieldtrackpro.android.ui.theme.LibreBaskervilleFamily,
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Normal,
                            color = com.fieldtrackpro.android.ui.theme.TextSecondary
                        )

                        Spacer(modifier = Modifier.height(12.dp))

                        Card(
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(180.dp),
                            shape = RoundedCornerShape(10.dp),
                            colors = CardDefaults.cardColors(containerColor = com.fieldtrackpro.android.ui.theme.SurfaceSecondary)
                        ) {
                            Column(
                                modifier = Modifier.fillMaxSize(),
                                horizontalAlignment = Alignment.CenterHorizontally,
                                verticalArrangement = Arrangement.Center
                            ) {
                                Text(
                                    text = "Photo captured successfully ✓",
                                    fontFamily = com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily,
                                    fontSize = 15.sp,
                                    color = com.fieldtrackpro.android.ui.theme.BrandNavy,
                                    fontWeight = FontWeight.Bold
                                )
                                Spacer(modifier = Modifier.height(4.dp))
                                Text(
                                    text = "Tap Save / Upload to attach to visit",
                                    fontFamily = com.fieldtrackpro.android.ui.theme.LibreBaskervilleFamily,
                                    fontSize = 13.sp,
                                    fontWeight = FontWeight.Normal,
                                    color = com.fieldtrackpro.android.ui.theme.TextSecondary
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
                                enabled = (state !is MediaState.Loading),
                                shape = RoundedCornerShape(8.dp)
                            ) {
                                Text("Retake", fontFamily = com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 13.sp, color = com.fieldtrackpro.android.ui.theme.BrandNavy)
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
                                    containerColor = com.fieldtrackpro.android.ui.theme.BrandNavy,
                                    contentColor = com.fieldtrackpro.android.ui.theme.BrandWhite
                                ),
                                enabled = (state !is MediaState.Loading),
                                shape = RoundedCornerShape(8.dp)
                            ) {
                                Text("Upload", fontFamily = com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 13.sp, color = com.fieldtrackpro.android.ui.theme.BrandWhite)
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))
            }

            // Upload Controls
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .border(1.dp, com.fieldtrackpro.android.ui.theme.BrandLightGray, RoundedCornerShape(14.dp)),
                shape = RoundedCornerShape(14.dp),
                colors = CardDefaults.cardColors(containerColor = com.fieldtrackpro.android.ui.theme.BrandWhite),
                elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
            ) {
                Column(modifier = Modifier.padding(18.dp)) {
                    Text(
                        text = if (isOrderMode) "Capture Order" else "Upload Attachment",
                        fontFamily = com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold,
                        color = com.fieldtrackpro.android.ui.theme.BrandNavy
                    )
                    Text(
                        text = if (isOrderMode)
                            "Photograph the order and add a short diary note."
                        else
                            "Upload site photos or documents (JPEG, PNG, PDF supported up to 10MB).",
                        fontFamily = com.fieldtrackpro.android.ui.theme.LibreBaskervilleFamily,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Normal,
                        color = com.fieldtrackpro.android.ui.theme.TextSecondary
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    if (isOrderMode) {
                        OutlinedTextField(
                            value = orderNote,
                            onValueChange = { 
                                orderNote = it
                                fieldError = null
                            },
                            placeholder = { 
                                Text(
                                    "Order note (e.g. 5x Usha fans, 2x Singer mixers)",
                                    fontFamily = com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily,
                                    fontSize = 14.sp,
                                    color = com.fieldtrackpro.android.ui.theme.TextSubtle
                                ) 
                            },
                            modifier = Modifier.fillMaxWidth(),
                            minLines = 3,
                            enabled = state !is MediaState.Loading,
                            shape = RoundedCornerShape(10.dp),
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedTextColor = com.fieldtrackpro.android.ui.theme.TextPrimary,
                                unfocusedTextColor = com.fieldtrackpro.android.ui.theme.TextPrimary,
                                focusedBorderColor = com.fieldtrackpro.android.ui.theme.BrandGold,
                                unfocusedBorderColor = com.fieldtrackpro.android.ui.theme.BrandLightGray,
                                focusedContainerColor = com.fieldtrackpro.android.ui.theme.BrandWhite,
                                unfocusedContainerColor = com.fieldtrackpro.android.ui.theme.BrandWhite
                            )
                        )
                        Spacer(modifier = Modifier.height(12.dp))

                        Text(
                            text = "ORDER PHOTO / INVOICE (OPTIONAL)",
                            fontFamily = com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily,
                            fontSize = 11.sp,
                            color = com.fieldtrackpro.android.ui.theme.TextSecondary,
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 0.8.sp
                        )
                        Spacer(modifier = Modifier.height(6.dp))

                        if (capturedPreviewUri != null) {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .background(com.fieldtrackpro.android.ui.theme.SurfaceSecondary, RoundedCornerShape(8.dp))
                                    .padding(8.dp),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    "Photo attached ✓",
                                    fontFamily = com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily,
                                    fontSize = 13.sp,
                                    color = com.fieldtrackpro.android.ui.theme.BrandNavy,
                                    fontWeight = FontWeight.Bold
                                )
                                OutlinedButton(
                                    onClick = { 
                                        capturedPreviewUri = null
                                        cameraUri = null
                                    },
                                    enabled = state !is MediaState.Loading,
                                    shape = RoundedCornerShape(6.dp)
                                ) {
                                    Text("Remove Photo", fontFamily = com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily, fontSize = 12.sp, fontWeight = FontWeight.Bold, color = com.fieldtrackpro.android.ui.theme.BrandNavy)
                                }
                            }
                            Spacer(modifier = Modifier.height(8.dp))
                        }
                    }

                    if (fieldError != null) {
                        ErrorBanner(message = fieldError!!)
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    if (state is MediaState.Error) {
                        ErrorBanner(message = (state as MediaState.Error).message)
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    if (state is MediaState.QueuedForRetry) {
                        Text(
                            text = "Queued for automatic retry - will upload once connection improves.",
                            fontFamily = com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily,
                            fontSize = 13.sp,
                            color = com.fieldtrackpro.android.ui.theme.BrandGoldDark,
                            fontWeight = FontWeight.Bold
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    if (state is MediaState.UploadSuccess) {
                        Text(
                            text = if (isOrderMode) "Order saved successfully!" else "Upload successful!",
                            fontFamily = com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily,
                            fontSize = 14.sp,
                            color = com.fieldtrackpro.android.ui.theme.BrandNavy,
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
                            shape = RoundedCornerShape(8.dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = com.fieldtrackpro.android.ui.theme.BrandNavy,
                                contentColor = com.fieldtrackpro.android.ui.theme.BrandWhite
                            ),
                            enabled = state !is MediaState.Loading
                        ) {
                            Text(
                                if (isOrderMode) "Attach Photo" else "Camera",
                                fontFamily = com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily,
                                fontWeight = FontWeight.Bold,
                                fontSize = 13.sp,
                                color = com.fieldtrackpro.android.ui.theme.BrandWhite
                            )
                        }

                        OutlinedButton(
                            onClick = { imagePickerLauncher.launch("image/*") },
                            modifier = Modifier.weight(1f),
                            shape = RoundedCornerShape(8.dp),
                            enabled = state !is MediaState.Loading
                        ) {
                            Text(
                                if (isOrderMode) "From Gallery" else "Photo",
                                fontFamily = com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily,
                                fontWeight = FontWeight.Bold,
                                fontSize = 13.sp,
                                color = com.fieldtrackpro.android.ui.theme.BrandNavy
                            )
                        }

                        if (!isOrderMode) {
                            OutlinedButton(
                                onClick = { documentPickerLauncher.launch("application/pdf") },
                                modifier = Modifier.weight(1f),
                                shape = RoundedCornerShape(8.dp),
                                enabled = state !is MediaState.Loading
                            ) {
                                Text(
                                    "PDF",
                                    fontFamily = com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily,
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 13.sp,
                                    color = com.fieldtrackpro.android.ui.theme.BrandNavy
                                )
                            }
                        }
                    }

                    if (isOrderMode) {
                        Spacer(modifier = Modifier.height(14.dp))
                        Button(
                            onClick = {
                                if (orderNote.isBlank() && capturedPreviewUri == null) {
                                    fieldError = "Please enter an order note or attach a photo."
                                } else {
                                    val uri = capturedPreviewUri
                                    if (uri != null) {
                                        dispatchUpload(uri, "image/jpeg")
                                        capturedPreviewUri = null
                                        cameraUri = null
                                    } else {
                                        uploadOrder(context, viewModel, visitId, Uri.EMPTY, "text/plain", orderNote)
                                    }
                                }
                            },
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(48.dp),
                            shape = RoundedCornerShape(8.dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = com.fieldtrackpro.android.ui.theme.BrandNavy,
                                contentColor = com.fieldtrackpro.android.ui.theme.BrandWhite
                            ),
                            enabled = state !is MediaState.Loading
                        ) {
                            Text(
                                "SAVE ORDER",
                                fontFamily = com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily,
                                fontWeight = FontWeight.Bold,
                                fontSize = 14.sp,
                                letterSpacing = 0.5.sp,
                                color = com.fieldtrackpro.android.ui.theme.BrandWhite
                            )
                        }
                    }

                    if (state is MediaState.Loading) {
                        Spacer(modifier = Modifier.height(12.dp))
                        CircularProgressIndicator(
                            modifier = Modifier.align(Alignment.CenterHorizontally),
                            color = com.fieldtrackpro.android.ui.theme.BrandGold
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(20.dp))

            // Existing Attachments / Orders Section
            Text(
                text = (if (isOrderMode) "Existing Orders" else "Existing Attachments").uppercase(),
                fontFamily = com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily,
                fontSize = 13.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 0.8.sp,
                color = com.fieldtrackpro.android.ui.theme.BrandNavy
            )

            Spacer(modifier = Modifier.height(10.dp))

            when (val s = state) {
                is MediaState.ListSuccess -> {
                    val items = s.items.filter { it.isOrder == isOrderMode }
                    if (items.isEmpty()) {
                        EmptyState(
                            title = if (isOrderMode) "No Orders" else "No Attachments",
                            subtitle = if (isOrderMode) "No orders captured for this visit yet." else "No files uploaded for this visit yet."
                        )
                    } else {
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            items.forEach { media ->
                                Card(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .border(1.dp, com.fieldtrackpro.android.ui.theme.BrandLightGray, RoundedCornerShape(12.dp))
                                        .clickable(enabled = !isOrderMode || media.hasPhotoAttachment) {
                                            onPreviewMedia(
                                                media.id,
                                                media.displayName,
                                                media.isPhoto
                                            )
                                        },
                                    shape = RoundedCornerShape(12.dp),
                                    colors = CardDefaults.cardColors(containerColor = com.fieldtrackpro.android.ui.theme.BrandWhite),
                                    elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
                                ) {
                                    Row(
                                        modifier = Modifier
                                            .padding(14.dp)
                                            .fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Column(modifier = Modifier.weight(1f).padding(end = 8.dp)) {
                                            Text(
                                                text = if (isOrderMode) media.orderText else media.displayName,
                                                fontFamily = com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily,
                                                fontSize = 15.sp,
                                                fontWeight = FontWeight.Bold,
                                                color = com.fieldtrackpro.android.ui.theme.BrandNavy
                                            )
                                            Spacer(modifier = Modifier.height(3.dp))
                                            Text(
                                                text = "Captured: ${media.uploadedAt.take(19).replace('T', ' ')}",
                                                fontFamily = com.fieldtrackpro.android.ui.theme.LibreBaskervilleFamily,
                                                fontSize = 13.sp,
                                                fontWeight = FontWeight.Normal,
                                                color = com.fieldtrackpro.android.ui.theme.TextSecondary
                                            )
                                        }
                                        StatusBadge(status = if (isOrderMode) (if (media.hasPhotoAttachment) "PHOTO ATTACHED" else "ORDER") else media.mediaType)
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

/** P2-B: order capture - routes through captureOrder with note. */
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
