package com.fieldtrackpro.android.ui.screens.proof

import android.graphics.Bitmap
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.OutletProofPayload
import com.fieldtrackpro.android.data.local.OutletProofStore
import com.fieldtrackpro.android.data.local.SyncConflict
import com.fieldtrackpro.android.data.repository.OutletProofMessages
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.SuccessGreen
import com.fieldtrackpro.android.ui.theme.SurfaceSecondary
import com.fieldtrackpro.android.ui.theme.TextSecondary
import com.fieldtrackpro.android.ui.viewmodel.OutletProofFlowViewModel
import com.fieldtrackpro.android.ui.viewmodel.ProofUi
import com.fieldtrackpro.android.utils.ImageDownsampler
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * "Outlet photo + GPS" card: the single place that shows the state of a live outlet proof (thumbnail, accuracy,
 * capture time, retake). Used by AddCustomerScreen and the existing-outlet dialog.
 */
@Composable
fun OutletProofCard(
    ui: ProofUi,
    onCapture: () -> Unit,
    onRetry: () -> Unit,
    onRetake: () -> Unit,
    emptyText: String = "A live photo of the outlet (shop board and front) with GPS is required. " +
        "Photos from the gallery are not accepted.",
    queuedHint: String = OutletProofMessages.QUEUED_OFFLINE
) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        when (ui) {
            is ProofUi.Empty -> {
                InfoBox(emptyText)
                Button(
                    onClick = onCapture,
                    modifier = Modifier.fillMaxWidth().height(46.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = BrandNavy),
                    shape = RoundedCornerShape(10.dp)
                ) {
                    Icon(Icons.Default.CameraAlt, contentDescription = null, tint = BrandWhite, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(8.dp))
                    Text("Take outlet photo", color = BrandWhite, fontWeight = FontWeight.Bold)
                }
            }
            is ProofUi.Uploading -> {
                CaptureSummary(ui.payload)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(modifier = Modifier.size(16.dp), strokeWidth = 2.dp, color = BrandNavy)
                    Spacer(Modifier.width(8.dp))
                    Text("Uploading photo and GPS…", fontSize = 12.sp, color = TextSecondary)
                }
            }
            is ProofUi.Uploaded -> {
                CaptureSummary(ui.payload)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.CheckCircle, contentDescription = null, tint = SuccessGreen, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(6.dp))
                    Text(OutletProofMessages.describeResult(ui.proof), fontSize = 12.sp, color = SuccessGreen, fontWeight = FontWeight.SemiBold)
                }
                OutlinedButton(onClick = onRetake, shape = RoundedCornerShape(8.dp)) {
                    Text("Retake photo", color = BrandNavy, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                }
            }
            is ProofUi.Queued -> {
                CaptureSummary(ui.payload)
                InfoBox(queuedHint)
            }
            is ProofUi.Failed -> {
                ui.payload?.let { CaptureSummary(it) }
                Text(ui.message, color = Color(0xFFC62828), fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (ui.canRetry) {
                        Button(
                            onClick = onRetry,
                            colors = ButtonDefaults.buttonColors(containerColor = BrandNavy),
                            shape = RoundedCornerShape(8.dp)
                        ) { Text("Try again", color = BrandWhite, fontWeight = FontWeight.Bold, fontSize = 12.sp) }
                    }
                    OutlinedButton(onClick = if (ui.payload != null) onRetake else onCapture, shape = RoundedCornerShape(8.dp)) {
                        Text("Retake photo", color = BrandNavy, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                    }
                }
            }
        }
    }
}

@Composable
private fun InfoBox(text: String) {
    Box(
        modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(6.dp)).background(SurfaceSecondary).padding(8.dp)
    ) { Text(text, fontSize = 11.sp, color = TextSecondary) }
}

/** Thumbnail + accuracy + capture time (no coordinates are shown or logged). */
@Composable
private fun CaptureSummary(payload: OutletProofPayload) {
    val bitmap by produceState<Bitmap?>(null, payload.photoPath) {
        value = withContext(Dispatchers.IO) {
            payload.photoPath?.let { path ->
                try {
                    File(path).takeIf { it.isFile }?.let { ImageDownsampler.decodeSampledBitmapForDisplay(it.readBytes(), 480) }
                } catch (e: Exception) { null }
            }
        }
    }
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            modifier = Modifier.size(84.dp).clip(RoundedCornerShape(8.dp)).background(SurfaceSecondary)
                .border(1.dp, Color(0x22000000), RoundedCornerShape(8.dp)),
            contentAlignment = Alignment.Center
        ) {
            bitmap?.let {
                Image(it.asImageBitmap(), contentDescription = "Outlet photo", contentScale = ContentScale.Crop, modifier = Modifier.size(84.dp))
            } ?: Icon(Icons.Default.CameraAlt, contentDescription = null, tint = TextSecondary)
        }
        Spacer(Modifier.width(12.dp))
        Column {
            Text("GPS accuracy ±%.0f m".format(payload.accuracyM ?: 0.0), fontSize = 13.sp, fontWeight = FontWeight.Bold, color = BrandNavy)
            payload.capturedAtEpochMs?.let {
                Text(
                    "Captured " + SimpleDateFormat("dd MMM, HH:mm:ss", Locale.getDefault()).format(Date(it)),
                    fontSize = 12.sp, color = TextSecondary
                )
            }
        }
    }
}

/**
 * RETAKE action for a queued proof that the server rejected as stale (or otherwise unusable). Captures a new live
 * photo for the same outlet, submits it, and on success removes the old conflict.
 */
@Composable
fun OutletProofRetakeAction(
    conflict: SyncConflict,
    offlineQueueManager: OfflineQueueManager,
    onResolved: () -> Unit
) {
    val payload = conflict.pendingAction.outletProofPayload ?: return
    val customerId = payload.customerId ?: return
    val vm: OutletProofFlowViewModel = viewModel(key = "outlet_proof_retake_$customerId")
    LaunchedEffect(customerId) { vm.start(customerId, payload.outletName, resetTerminal = true) }
    val ui by vm.ui.collectAsState()
    val capture = rememberOutletProofCapture(customerId, payload.outletName) { vm.onCaptured(it) }

    LaunchedEffect(ui) {
        if (ui is ProofUi.Uploaded || ui is ProofUi.Queued) {
            OutletProofStore.delete(payload.photoPath)
            offlineQueueManager.removeAction(conflict.pendingAction.id)
            offlineQueueManager.removeConflict(conflict.id)
            onResolved()
        }
    }
    OutletProofCard(
        ui = ui,
        onCapture = capture,
        onRetry = { vm.retryUpload() },
        onRetake = { vm.discard(); capture() },
        emptyText = "Take a new live photo at the outlet to replace the rejected one."
    )
}
