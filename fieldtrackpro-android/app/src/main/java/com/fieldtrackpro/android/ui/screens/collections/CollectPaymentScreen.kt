package com.fieldtrackpro.android.ui.screens.collections

import android.Manifest
import android.content.pm.PackageManager
import android.net.Uri
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
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import com.fieldtrackpro.android.ui.components.ErrorBanner
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.theme.FieldTrackNavy
import com.fieldtrackpro.android.ui.theme.SuccessGreen
import com.fieldtrackpro.android.ui.theme.SurfaceOffWhite
import com.fieldtrackpro.android.ui.theme.SurfaceWhite
import com.fieldtrackpro.android.ui.theme.TextMuted
import com.fieldtrackpro.android.ui.theme.TextPrimary
import com.fieldtrackpro.android.ui.viewmodel.CollectionState
import com.fieldtrackpro.android.ui.viewmodel.CollectionViewModel
import kotlinx.coroutines.launch
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

private val PAYMENT_METHODS = listOf("CASH", "CHEQUE", "ONLINE")

private fun todayIso(): String = SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())

private fun createTempImageUri(context: android.content.Context): Uri {
    val tempFile = File.createTempFile("proof_${System.currentTimeMillis()}", ".jpg", context.cacheDir)
    return FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", tempFile)
}

/**
 * Employee collection capture: amount + method (cash/cheque/online) with
 * method-specific fields, payment date, and an optional proof photo (cheque
 * photo or payment screenshot). Submits as PENDING_VERIFICATION - an
 * admin/accountant must verify it before it counts toward the outlet's
 * paid/outstanding totals (see backend payment_service.py).
 */
@Composable
fun CollectPaymentScreen(
    visitId: String,
    customerId: String,
    viewModel: CollectionViewModel,
    onNavigateBack: () -> Unit,
    onSuccess: () -> Unit,
) {
    val context = LocalContext.current
    val coroutineScope = rememberCoroutineScope()
    val state by viewModel.collectionState.collectAsState()

    var amount by remember { mutableStateOf("") }
    var method by remember { mutableStateOf("CASH") }
    var paymentDate by remember { mutableStateOf(todayIso()) }
    var chequeNumber by remember { mutableStateOf("") }
    var chequeBankName by remember { mutableStateOf("") }
    var utrReference by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    var proofUri by remember { mutableStateOf<Uri?>(null) }
    var cameraUri by remember { mutableStateOf<Uri?>(null) }
    var fieldError by remember { mutableStateOf<String?>(null) }
    var isUploadingProof by remember { mutableStateOf(false) }

    var hasCameraPermission by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
        )
    }

    val cameraLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.TakePicture()
    ) { success ->
        if (success && cameraUri != null) proofUri = cameraUri
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

    fun capturePhoto() {
        if (hasCameraPermission) {
            val uri = createTempImageUri(context)
            cameraUri = uri
            cameraLauncher.launch(uri)
        } else {
            permissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    Scaffold(
        topBar = { FieldTrackTopAppBar(title = "Collect Payment", onBackClick = onNavigateBack) }
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(SurfaceOffWhite)
                .padding(innerPadding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState())
        ) {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
            ) {
                Column(modifier = Modifier.padding(20.dp)) {
                    fieldError?.let {
                        ErrorBanner(message = it)
                        Spacer(modifier = Modifier.height(12.dp))
                    }
                    if (state is CollectionState.Error) {
                        ErrorBanner(message = (state as CollectionState.Error).message)
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    OutlinedTextField(
                        value = amount,
                        onValueChange = { amount = it },
                        label = { Text("Amount (₹)") },
                        modifier = Modifier.fillMaxWidth()
                    )
                    Spacer(modifier = Modifier.height(12.dp))

                    Text("PAYMENT METHOD", fontSize = 11.sp, color = TextMuted, fontWeight = FontWeight.SemiBold)
                    Spacer(modifier = Modifier.height(6.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        PAYMENT_METHODS.forEach { m ->
                            val selected = method == m
                            OutlinedButton(
                                onClick = { method = m },
                                colors = ButtonDefaults.outlinedButtonColors(
                                    containerColor = if (selected) FieldTrackNavy else SurfaceWhite,
                                    contentColor = if (selected) SurfaceWhite else TextPrimary
                                ),
                                modifier = Modifier.weight(1f)
                            ) { Text(m, fontSize = 12.sp) }
                        }
                    }
                    Spacer(modifier = Modifier.height(12.dp))

                    OutlinedTextField(
                        value = paymentDate,
                        onValueChange = { paymentDate = it },
                        label = { Text("Payment Date (YYYY-MM-DD)") },
                        modifier = Modifier.fillMaxWidth()
                    )
                    Spacer(modifier = Modifier.height(12.dp))

                    if (method == "CHEQUE") {
                        OutlinedTextField(
                            value = chequeNumber,
                            onValueChange = { chequeNumber = it },
                            label = { Text("Cheque Number") },
                            modifier = Modifier.fillMaxWidth()
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                        OutlinedTextField(
                            value = chequeBankName,
                            onValueChange = { chequeBankName = it },
                            label = { Text("Bank Name") },
                            modifier = Modifier.fillMaxWidth()
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    if (method == "ONLINE") {
                        OutlinedTextField(
                            value = utrReference,
                            onValueChange = { utrReference = it },
                            label = { Text("UTR / Reference Number") },
                            modifier = Modifier.fillMaxWidth()
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    Text(
                        if (method == "CHEQUE") "CHEQUE PHOTO" else if (method == "ONLINE") "PAYMENT SCREENSHOT" else "RECEIPT PHOTO (OPTIONAL)",
                        fontSize = 11.sp, color = TextMuted, fontWeight = FontWeight.SemiBold
                    )
                    Spacer(modifier = Modifier.height(6.dp))
                    if (proofUri != null) {
                        Text("Photo captured ✓", fontSize = 12.sp, color = SuccessGreen)
                        Spacer(modifier = Modifier.height(6.dp))
                    }
                    OutlinedButton(onClick = { capturePhoto() }, modifier = Modifier.fillMaxWidth()) {
                        Text(if (proofUri == null) "CAPTURE PHOTO" else "RETAKE PHOTO", color = FieldTrackNavy)
                    }
                    Spacer(modifier = Modifier.height(12.dp))

                    OutlinedTextField(
                        value = notes,
                        onValueChange = { notes = it },
                        label = { Text("Notes (optional)") },
                        modifier = Modifier.fillMaxWidth()
                    )
                    Spacer(modifier = Modifier.height(20.dp))

                    Button(
                        onClick = {
                            fieldError = null
                            val parsedAmount = amount.toDoubleOrNull()
                            if (parsedAmount == null || parsedAmount <= 0) {
                                fieldError = "Enter a valid payment amount."
                                return@Button
                            }
                            if (method == "CHEQUE" && chequeNumber.isBlank()) {
                                fieldError = "Cheque number is required for cheque payments."
                                return@Button
                            }
                            if (method == "ONLINE" && utrReference.isBlank()) {
                                fieldError = "UTR reference is required for online payments."
                                return@Button
                            }
                            viewModel.submitCollection(
                                visitId = visitId,
                                invoiceId = null,
                                amount = amount,
                                paymentMethod = method,
                                paymentDate = paymentDate,
                                chequeNumber = if (method == "CHEQUE") chequeNumber else null,
                                chequeBankName = if (method == "CHEQUE") chequeBankName.ifBlank { null } else null,
                                utrReference = if (method == "ONLINE") utrReference else null,
                                notes = notes.ifBlank { null },
                                onSubmitted = { payment ->
                                    val uri = proofUri
                                    if (uri != null) {
                                        coroutineScope.launch {
                                            isUploadingProof = true
                                            try {
                                                val bytes = context.contentResolver.openInputStream(uri)?.readBytes()
                                                if (bytes != null && bytes.isNotEmpty()) {
                                                    viewModel.uploadProof(payment.id, "proof_${payment.id}.jpg", "image/jpeg", bytes)
                                                }
                                            } finally {
                                                isUploadingProof = false
                                                onSuccess()
                                            }
                                        }
                                    } else {
                                        onSuccess()
                                    }
                                }
                            )
                        },
                        modifier = Modifier.fillMaxWidth().height(50.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = FieldTrackNavy, contentColor = SurfaceWhite),
                        enabled = state !is CollectionState.Submitting && !isUploadingProof
                    ) {
                        if (state is CollectionState.Submitting || isUploadingProof) {
                            CircularProgressIndicator(color = SurfaceWhite, modifier = Modifier.height(20.dp))
                        } else {
                            Text("RECORD COLLECTION", fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }
    }
}
