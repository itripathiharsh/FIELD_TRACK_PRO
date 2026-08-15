package com.fieldtrackpro.android.ui.screens.signature

import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
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
import com.fieldtrackpro.android.data.model.SignatureDto
import com.fieldtrackpro.android.ui.components.ErrorBanner
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.components.rememberFilePicker
import com.fieldtrackpro.android.ui.theme.CoralRed
import com.fieldtrackpro.android.ui.theme.FieldTrackAmber
import com.fieldtrackpro.android.ui.theme.FieldTrackNavy
import com.fieldtrackpro.android.ui.theme.SurfaceOffWhite
import com.fieldtrackpro.android.ui.theme.SurfaceWhite
import com.fieldtrackpro.android.ui.theme.TextMuted
import com.fieldtrackpro.android.ui.viewmodel.SignatureState
import com.fieldtrackpro.android.ui.viewmodel.SignatureViewModel
import com.fieldtrackpro.android.utils.ImageDownsampler
import kotlinx.coroutines.launch

/** How the customer is providing their acknowledgement in this session. */
private enum class CustomerAckMode { SIGN, PHOTO }

@Composable
fun SignatureScreen(
    visitId: String,
    viewModel: SignatureViewModel,
    onNavigateBack: () -> Unit,
    onComplete: () -> Unit
) {
    val state by viewModel.signatureState.collectAsState()
    val context = LocalContext.current
    val employeeSignatureState = rememberSignatureCaptureState()
    val customerSignatureState = rememberSignatureCaptureState()
    val coroutineScope = rememberCoroutineScope()

    // Existing CURRENT signatures for this visit, so a re-visit of this
    // screen doesn't silently 409 on re-submit and instead offers "Redo"
    // (replace) - kept in local state because upload/replace also drive
    // `state` through Loading/Success, which would otherwise clobber this.
    var existingSignatures by remember { mutableStateOf<List<SignatureDto>>(emptyList()) }
    var redoEmployee by remember { mutableStateOf(false) }
    var redoCustomer by remember { mutableStateOf(false) }
    var customerMode by remember { mutableStateOf<CustomerAckMode?>(null) }
    var customerPhotoUri by remember { mutableStateOf<Uri?>(null) }

    LaunchedEffect(visitId) {
        viewModel.loadVisitSignatures(visitId)
    }

    LaunchedEffect(state) {
        val current = state
        if (current is SignatureState.ListSuccess) {
            existingSignatures = current.items
        }
    }

    val existingEmployee = existingSignatures.firstOrNull { it.isEmployee && !it.isSuperseded }
    val existingCustomer = existingSignatures.firstOrNull { it.isCustomer && !it.isSuperseded }
    val showEmployeeCapture = existingEmployee == null || redoEmployee
    val showCustomerCapture = existingCustomer == null || redoCustomer

    val photoPicker = rememberFilePicker(
        onFileSelected = { uri, _ -> customerPhotoUri = uri },
        mimeType = "image/*",
    )

    Scaffold(
        topBar = {
            FieldTrackTopAppBar(
                title = "Signatures & Acknowledgement",
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
            Text(
                text = "Visit Completion",
                style = MaterialTheme.typography.titleLarge,
                color = FieldTrackNavy
            )
            Text(
                text = "Both are optional and won't block completing this visit.",
                style = MaterialTheme.typography.bodyMedium,
                color = TextMuted
            )

            Spacer(modifier = Modifier.height(16.dp))

            if (state is SignatureState.Error) {
                ErrorBanner(message = (state as SignatureState.Error).message)
                Spacer(modifier = Modifier.height(12.dp))
            }

            // P1-6: queued for automatic background retry, not lost.
            if (state is SignatureState.QueuedForRetry) {
                Text(
                    text = "Queued for automatic retry - will upload once connection improves.",
                    fontSize = 13.sp,
                    color = FieldTrackAmber,
                    fontWeight = FontWeight.Bold
                )
                Spacer(modifier = Modifier.height(12.dp))
            }

            if (state is SignatureState.UploadSuccess) {
                Text(
                    text = "Saved!",
                    fontSize = 13.sp,
                    color = FieldTrackNavy,
                    fontWeight = FontWeight.Bold
                )
                Spacer(modifier = Modifier.height(12.dp))
            }

            // Employee signature - unchanged canvas-only capture.
            if (showEmployeeCapture) {
                SignatureCaptureSection(
                    title = "Employee Signature (optional)",
                    state = employeeSignatureState,
                    onClear = { employeeSignatureState.clear() }
                )
            } else {
                CapturedSummaryCard(
                    title = "Employee signature already captured",
                    onRedo = {
                        redoEmployee = true
                        employeeSignatureState.clear()
                    }
                )
            }

            Spacer(modifier = Modifier.height(16.dp))

            // Customer acknowledgement - either drawn live on this device, or
            // a photo of an already-signed paper document. Neither collects
            // any customer identity information (no phone/OTP/ID/email) -
            // this only records that *an* acknowledgement was captured and by
            // which employee account, not a verified identity of the signer.
            Text(
                text = "Customer Acknowledgement (optional)",
                fontSize = 14.sp,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onSurface
            )
            if (!showCustomerCapture) {
                Spacer(modifier = Modifier.height(8.dp))
                CapturedSummaryCard(
                    title = if (existingCustomer?.isPhotoUpload == true) {
                        "Customer acknowledgement already uploaded"
                    } else {
                        "Customer signature already captured"
                    },
                    onRedo = {
                        redoCustomer = true
                        customerMode = null
                        customerPhotoUri = null
                        customerSignatureState.clear()
                    }
                )
            } else if (customerMode == null) {
                Text(
                    text = "Only use \"Sign on Screen\" if the customer is signing themselves, right now.",
                    fontSize = 12.sp,
                    color = TextMuted
                )
                Spacer(modifier = Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    OutlinedButton(
                        onClick = { customerMode = CustomerAckMode.SIGN },
                        modifier = Modifier.weight(1f)
                    ) { Text("Sign on Screen") }
                    OutlinedButton(
                        onClick = { customerMode = CustomerAckMode.PHOTO },
                        modifier = Modifier.weight(1f)
                    ) { Text("Upload Photo") }
                }
            } else {
                Spacer(modifier = Modifier.height(8.dp))
                when (customerMode) {
                    CustomerAckMode.SIGN -> {
                        SignatureCaptureSection(
                            title = "Have the customer sign below",
                            state = customerSignatureState,
                            onClear = { customerSignatureState.clear() }
                        )
                    }
                    CustomerAckMode.PHOTO -> {
                        Text(
                            text = if (customerPhotoUri != null) "Photo selected" else "No photo selected yet",
                            fontSize = 13.sp,
                            color = TextMuted
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        OutlinedButton(onClick = photoPicker) {
                            Text(if (customerPhotoUri != null) "Choose a different photo" else "Choose Photo")
                        }
                    }
                    null -> {}
                }
                Spacer(modifier = Modifier.height(4.dp))
                TextButton(onClick = { customerMode = null; customerPhotoUri = null; customerSignatureState.clear() }) {
                    Text("Change method", fontSize = 12.sp)
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            Button(
                onClick = {
                    coroutineScope.launch {
                        var allOk = true

                        if (!employeeSignatureState.isEmpty) {
                            val bytes = employeeSignatureState.toPngBytes(600, 200)
                            val ok = if (existingEmployee != null && redoEmployee) {
                                viewModel.replaceSignatureAwait(visitId, existingEmployee.id, bytes, "SIGNATURE")
                            } else {
                                viewModel.uploadSignatureAwait(visitId, "EMPLOYEE", bytes, "SIGNATURE")
                            }
                            allOk = ok && allOk
                        }

                        when (customerMode) {
                            CustomerAckMode.SIGN -> if (!customerSignatureState.isEmpty) {
                                val bytes = customerSignatureState.toPngBytes(600, 200)
                                val ok = if (existingCustomer != null && redoCustomer) {
                                    viewModel.replaceSignatureAwait(visitId, existingCustomer.id, bytes, "SIGNATURE")
                                } else {
                                    viewModel.uploadSignatureAwait(visitId, "CUSTOMER", bytes, "SIGNATURE")
                                }
                                allOk = ok && allOk
                            }
                            CustomerAckMode.PHOTO -> customerPhotoUri?.let { uri ->
                                val bytes = ImageDownsampler.downsample(context, uri)
                                if (bytes == null) {
                                    allOk = false
                                } else {
                                    val ok = if (existingCustomer != null && redoCustomer) {
                                        viewModel.replaceSignatureAwait(visitId, existingCustomer.id, bytes, "PHOTO_UPLOAD")
                                    } else {
                                        viewModel.uploadSignatureAwait(visitId, "CUSTOMER", bytes, "PHOTO_UPLOAD")
                                    }
                                    allOk = ok && allOk
                                }
                            }
                            null -> {}
                        }

                        // Only leave the screen once every capture that was
                        // attempted actually succeeded - a failed upload now
                        // keeps the user here with the error visible instead
                        // of silently completing the visit without it. Both
                        // sections being empty is a valid "skip both" submit.
                        if (allOk) onComplete()
                    }
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(50.dp),
                shape = RoundedCornerShape(8.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = FieldTrackNavy,
                    contentColor = SurfaceWhite
                ),
                enabled = state !is SignatureState.Loading
            ) {
                Text("SUBMIT", fontWeight = FontWeight.Bold, color = SurfaceWhite)
            }

            Spacer(modifier = Modifier.height(8.dp))

            Button(
                onClick = onNavigateBack,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(50.dp),
                shape = RoundedCornerShape(8.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = CoralRed,
                    contentColor = SurfaceWhite
                )
            ) {
                Text("CANCEL", fontWeight = FontWeight.Bold, color = SurfaceWhite)
            }
        }
    }
}

@Composable
private fun CapturedSummaryCard(title: String, onRedo: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text(text = title, fontSize = 13.sp, color = FieldTrackNavy, modifier = Modifier.weight(1f))
            TextButton(onClick = onRedo) { Text("Redo") }
        }
    }
}
