package com.fieldtrackpro.android.ui.components

import android.content.Context
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.MutableState
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.FileProvider
import java.io.File

/**
 * Creates a temporary file for camera capture and returns its URI via FileProvider.
 */
fun createImageUri(context: Context): Uri {
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
 * Launches camera capture. Returns the URI where the photo should be stored.
 */
@Composable
fun rememberCameraPicker(
    onPhotoCaptured: (Uri) -> Unit,
): () -> Unit {
    val context = LocalContext.current
    val cameraUriState: MutableState<Uri?> = remember { mutableStateOf(null) }

    val cameraLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.TakePicture()
    ) { success ->
        if (success) {
            cameraUriState.value?.let { onPhotoCaptured(it) }
        }
    }

    return remember {
        {
            val uri = createImageUri(context)
            cameraUriState.value = uri
            cameraLauncher.launch(uri)
        }
    }
}

/**
 * Launches file picker for images or documents.
 */
@Composable
fun rememberFilePicker(
    onFileSelected: (Uri, String) -> Unit,
    mimeType: String = "image/*",
): () -> Unit {
    val context = LocalContext.current

    val filePickerLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.GetContent()
    ) { uri ->
        if (uri != null) {
            val detectedMime = context.contentResolver.getType(uri) ?: mimeType
            onFileSelected(uri, detectedMime)
        }
    }

    return remember {
        { filePickerLauncher.launch(mimeType) }
    }
}
