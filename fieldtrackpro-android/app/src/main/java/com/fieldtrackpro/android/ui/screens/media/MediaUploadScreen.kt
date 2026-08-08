package com.fieldtrackpro.android.ui.screens.media

import android.Manifest
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
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
import androidx.compose.material3.OutlinedButton
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
import com.fieldtrackpro.android.ui.theme.ElectricBlue
import com.fieldtrackpro.android.ui.theme.Slate50
import com.fieldtrackpro.android.ui.theme.Slate500
import com.fieldtrackpro.android.ui.theme.Slate900
import com.fieldtrackpro.android.ui.theme.SurfaceWhite
import com.fieldtrackpro.android.ui.viewmodel.MediaState
import com.fieldtrackpro.android.ui.viewmodel.MediaViewModel
import java.io.File

@Composable
fun MediaUploadScreen(
    visitId: String,
    viewModel: MediaViewModel,
    onNavigateBack: () -> Unit
) {
    val context = LocalContext.current
    val state by viewModel.mediaState.collectAsState()

    var cameraUri by remember { mutableStateOf<Uri?>(null) }
    var hasCameraPermission by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) ==
                PackageManager.PERMISSION_GRANTED
        )
    }

    val cameraLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.TakePicture()
    ) { success ->
        if (success && cameraUri != null) {
            uploadFile(context, viewModel, visitId, cameraUri!!, "image/jpeg")
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
            uploadFile(context, viewModel, visitId, uri, mimeType)
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
                title = "Visit Media & Attachments",
                onBackClick = onNavigateBack
            )
        }
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(Slate50)
                .padding(innerPadding)
                .padding(20.dp)
        ) {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
            ) {
                Column(modifier = Modifier.padding(20.dp)) {
                    Text(
                        text = "Upload Attachment",
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold,
                        color = Slate900
                    )
                    Text(
                        text = "Upload site photos or documents (JPEG, PNG, PDF supported up to 10MB).",
                        fontSize = 13.sp,
                        color = Slate500
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    if (state is MediaState.Error) {
                        ErrorBanner(message = (state as MediaState.Error).message)
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    if (state is MediaState.UploadSuccess) {
                        Text(
                            text = "Upload successful!",
                            fontSize = 13.sp,
                            color = ElectricBlue,
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
                                if (hasCameraPermission) {
                                    val uri = createTempImageUri(context)
                                    cameraUri = uri
                                    cameraLauncher.launch(uri)
                                } else {
                                    permissionLauncher.launch(Manifest.permission.CAMERA)
                                }
                            },
                            modifier = Modifier.weight(1f),
                            colors = ButtonDefaults.buttonColors(containerColor = ElectricBlue),
                            enabled = state !is MediaState.Loading
                        ) {
                            Text("Camera", fontSize = 12.sp)
                        }

                        OutlinedButton(
                            onClick = { imagePickerLauncher.launch("image/*") },
                            modifier = Modifier.weight(1f),
                            enabled = state !is MediaState.Loading
                        ) {
                            Text("Photo", fontSize = 12.sp)
                        }

                        OutlinedButton(
                            onClick = { documentPickerLauncher.launch("application/pdf") },
                            modifier = Modifier.weight(1f),
                            enabled = state !is MediaState.Loading
                        ) {
                            Text("PDF", fontSize = 12.sp)
                        }
                    }

                    if (state is MediaState.Loading) {
                        Spacer(modifier = Modifier.height(12.dp))
                        CircularProgressIndicator(
                            modifier = Modifier.align(Alignment.CenterHorizontally)
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            Text(
                text = "Existing Attachments",
                fontSize = 16.sp,
                fontWeight = FontWeight.Bold,
                color = Slate900
            )

            Spacer(modifier = Modifier.height(12.dp))

            when (val s = state) {
                is MediaState.ListSuccess -> {
                    val items = s.items
                    if (items.isEmpty()) {
                        EmptyState(title = "No Attachments", subtitle = "No files uploaded for this visit yet.")
                    } else {
                        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            items(items) { media ->
                                Card(
                                    modifier = Modifier.fillMaxWidth(),
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
                                                color = Slate900
                                            )
                                            Text(
                                                text = "Size: ${media.fileSizeBytes} bytes | Type: ${media.mediaType}",
                                                fontSize = 12.sp,
                                                color = Slate500
                                            )
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

private fun uploadFile(
    context: android.content.Context,
    viewModel: MediaViewModel,
    visitId: String,
    uri: Uri,
    mimeType: String
) {
    try {
        val inputStream = context.contentResolver.openInputStream(uri)
        val bytes = inputStream?.readBytes()
        inputStream?.close()

        if (bytes != null && bytes.isNotEmpty()) {
            val fileName = uri.lastPathSegment ?: "attachment_${System.currentTimeMillis()}"
            viewModel.uploadMedia(visitId, fileName, mimeType, bytes)
        }
    } catch (e: Exception) {
        // Error will be handled by the ViewModel state
    }
}
