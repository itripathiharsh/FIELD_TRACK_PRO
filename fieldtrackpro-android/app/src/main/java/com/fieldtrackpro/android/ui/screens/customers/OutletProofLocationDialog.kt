package com.fieldtrackpro.android.ui.screens.customers

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.fieldtrackpro.android.ui.screens.proof.OutletProofCard
import com.fieldtrackpro.android.ui.screens.proof.rememberOutletProofCapture
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.TextSecondary
import com.fieldtrackpro.android.ui.viewmodel.OutletProofFlowViewModel
import com.fieldtrackpro.android.ui.viewmodel.ProofUi

/**
 * Existing-outlet location suggestion with LIVE proof: the rep takes a camera photo, the GPS fix is captured at the
 * shutter click, and both are uploaded as one bundle with the customer id. The backend decides whether it is a
 * confirmation, an initial pin or a change request (admin approval); coordinates are never overwritten directly.
 */
@Composable
fun OutletProofLocationDialog(
    customerId: String,
    customerName: String,
    /** True when the outlet already has GPS: the suggestion is then a CHANGE that an admin must approve. */
    hasLocation: Boolean = true,
    onDismiss: () -> Unit
) {
    val vm: OutletProofFlowViewModel = viewModel(key = "outlet_proof_$customerId")
    LaunchedEffect(customerId) { vm.start(customerId, customerName, resetTerminal = true) }
    val ui by vm.ui.collectAsState()
    val capture = rememberOutletProofCapture(customerId, customerName) { vm.onCaptured(it) }
    val busy = ui is ProofUi.Uploading

    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        shape = RoundedCornerShape(16.dp),
        title = {
            Column {
                Text(if (hasLocation) "Suggest a different location" else "Suggest outlet location", fontWeight = FontWeight.Bold, fontSize = 17.sp, color = BrandNavy)
                Text(customerName, fontSize = 12.sp, color = TextSecondary)
            }
        },
        text = {
            Column(
                modifier = Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(vertical = 4.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Text(
                    if (hasLocation) {
                        "Stand at the outlet and take a live photo of the shop board and front. Your GPS position is " +
                            "recorded when you press the shutter. This outlet already has a location, so an admin " +
                            "reviews the change before it is used. Until then the current location stays."
                    } else {
                        "This outlet has no GPS location yet. Stand at the shop and take a live photo of the shop board " +
                            "and front. Your GPS position is recorded when you press the shutter and, if the photo and " +
                            "GPS are good, saved as the outlet's location straight away. Checking in is a separate step."
                    },
                    fontSize = 12.sp, color = TextSecondary
                )
                OutletProofCard(
                    ui = ui,
                    onCapture = capture,
                    onRetry = { vm.retryUpload() },
                    onRetake = { vm.discard(); capture() }
                )
            }
        },
        confirmButton = {
            val done = ui is ProofUi.Uploaded || ui is ProofUi.Queued
            Button(
                onClick = onDismiss,
                enabled = !busy,
                colors = ButtonDefaults.buttonColors(containerColor = BrandNavy),
                shape = RoundedCornerShape(10.dp)
            ) { Text(if (done) "Done" else "Close", color = BrandWhite, fontWeight = FontWeight.Bold, fontSize = 13.sp) }
        },
        dismissButton = {}
    )
}
