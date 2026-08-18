package com.fieldtrackpro.android.ui.screens.signature

import android.graphics.Bitmap
import android.net.Uri
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.data.model.SignatureDto
import com.fieldtrackpro.android.ui.components.ErrorBanner
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.components.rememberFilePicker
import com.fieldtrackpro.android.ui.theme.BrandBlack
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandLightGray
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.ErrorRed
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.theme.LibreBaskervilleFamily
import com.fieldtrackpro.android.ui.theme.SuccessGreen
import com.fieldtrackpro.android.ui.theme.SurfaceSecondary
import com.fieldtrackpro.android.ui.theme.TextPrimary
import com.fieldtrackpro.android.ui.theme.TextSecondary
import com.fieldtrackpro.android.ui.viewmodel.SignatureState
import com.fieldtrackpro.android.ui.viewmodel.SignatureViewModel
import com.fieldtrackpro.android.utils.ImageDownsampler
import kotlinx.coroutines.launch

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
    val employeeSignatureState = viewModel.employeeSignatureState
    val customerSignatureState = viewModel.customerSignatureState
    val coroutineScope = rememberCoroutineScope()

    var existingSignatures by remember { mutableStateOf<List<SignatureDto>>(emptyList()) }
    var redoEmployee by remember { mutableStateOf(false) }
    var redoCustomer by remember { mutableStateOf(false) }
    var customerMode by remember { mutableStateOf<CustomerAckMode?>(null) }
    var customerPhotoUri by remember { mutableStateOf<Uri?>(null) }
    
    var employeeSavedBitmap by remember { mutableStateOf<Bitmap?>(null) }
    var customerSavedBitmap by remember { mutableStateOf<Bitmap?>(null) }

    var isSigningEmployee by remember { mutableStateOf(false) }
    var isSigningCustomer by remember { mutableStateOf(false) }

    LaunchedEffect(visitId) {
        viewModel.loadVisitSignatures(visitId)
    }

    LaunchedEffect(state) {
        val current = state
        if (current is SignatureState.ListSuccess) {
            existingSignatures = current.items
        }
    }

    if (isSigningEmployee) {
        FullScreenSignatureCapture(
            title = "Employee Signature",
            state = employeeSignatureState,
            onSave = {
                val bmp = employeeSignatureState.toBitmap(600, 200)
                employeeSavedBitmap = bmp
                isSigningEmployee = false
            },
            onClear = { employeeSignatureState.clear() },
            onCancel = {
                isSigningEmployee = false
            }
        )
        return
    }

    if (isSigningCustomer) {
        FullScreenSignatureCapture(
            title = "Customer Signature",
            state = customerSignatureState,
            onSave = {
                val bmp = customerSignatureState.toBitmap(600, 200)
                customerSavedBitmap = bmp
                isSigningCustomer = false
            },
            onClear = { customerSignatureState.clear() },
            onCancel = {
                isSigningCustomer = false
            }
        )
        return
    }

    val existingEmployee = existingSignatures.firstOrNull { it.isEmployee && !it.isSuperseded }
    val existingCustomer = existingSignatures.firstOrNull { it.isCustomer && !it.isSuperseded }
    val showEmployeeCapture = (existingEmployee == null || redoEmployee) && employeeSavedBitmap == null
    val showCustomerCapture = (existingCustomer == null || redoCustomer) && customerSavedBitmap == null

    val photoPicker = rememberFilePicker(
        onFileSelected = { uri, _ -> customerPhotoUri = uri },
        mimeType = "image/*",
    )

    Scaffold(
        topBar = {
            FieldTrackTopAppBar(
                title = "Digital Signatures",
                onBackClick = onNavigateBack
            )
        }
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(SurfaceSecondary)
                .padding(innerPadding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState())
        ) {
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .border(1.dp, BrandLightGray, RoundedCornerShape(14.dp)),
                shape = RoundedCornerShape(14.dp),
                colors = CardDefaults.cardColors(containerColor = BrandWhite),
                elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
            ) {
                Column(modifier = Modifier.padding(18.dp)) {
                    Text(
                        text = "Visit Sign-Off & Authorization",
                        fontFamily = LeagueSpartanFamily,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold,
                        color = BrandNavy
                    )
                    Text(
                        text = "Capture representative and customer sign-off or photo proof of visit acknowledgement.",
                        fontFamily = LibreBaskervilleFamily,
                        fontSize = 13.sp,
                        color = TextSecondary
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    if (state is SignatureState.Error) {
                        ErrorBanner(message = (state as SignatureState.Error).message)
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    if (state is SignatureState.QueuedForRetry) {
                        Text(
                            text = "Queued for automatic retry — will upload once network is reachable.",
                            fontFamily = LeagueSpartanFamily,
                            fontSize = 13.sp,
                            color = BrandGold,
                            fontWeight = FontWeight.Bold
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    // Employee signature section
                    Text(
                        text = "EMPLOYEE SIGNATURE",
                        fontFamily = LeagueSpartanFamily,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 0.8.sp,
                        color = BrandNavy
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    if (showEmployeeCapture) {
                        OutlinedButton(
                            onClick = { 
                                employeeSignatureState.clear()
                                isSigningEmployee = true 
                            },
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(8.dp),
                            border = ButtonDefaults.outlinedButtonBorder.copy(
                                brush = androidx.compose.ui.graphics.SolidColor(BrandLightGray)
                            )
                        ) {
                            Text(
                                "DRAW EMPLOYEE SIGNATURE",
                                fontFamily = LeagueSpartanFamily,
                                fontWeight = FontWeight.Bold,
                                color = BrandNavy
                            )
                        }
                    } else {
                        CapturedSummaryCard(
                            title = "Employee Signature Recorded",
                            savedBitmap = employeeSavedBitmap,
                            isAlreadyUploaded = existingEmployee != null && !redoEmployee,
                            onRedo = { 
                                redoEmployee = true
                                employeeSavedBitmap = null
                                employeeSignatureState.clear()
                                isSigningEmployee = true 
                            }
                        )
                    }

                    Spacer(modifier = Modifier.height(18.dp))

                    // Customer signature section
                    Text(
                        text = "CUSTOMER ACKNOWLEDGEMENT",
                        fontFamily = LeagueSpartanFamily,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 0.8.sp,
                        color = BrandNavy
                    )
                    if (!showCustomerCapture) {
                        Spacer(modifier = Modifier.height(8.dp))
                        CapturedSummaryCard(
                            title = if (customerPhotoUri != null || existingCustomer?.isPhotoUpload == true) {
                                "Customer Photo Proof Recorded"
                            } else {
                                "Customer Signature Recorded"
                            },
                            savedBitmap = customerSavedBitmap,
                            isAlreadyUploaded = existingCustomer != null && !redoCustomer,
                            onRedo = {
                                redoCustomer = true
                                customerMode = null
                                customerPhotoUri = null
                                customerSavedBitmap = null
                                customerSignatureState.clear()
                            }
                        )
                    } else if (customerMode == null) {
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = "Select acknowledgement method:",
                            fontFamily = LibreBaskervilleFamily,
                            fontSize = 12.sp,
                            color = TextSecondary
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            OutlinedButton(
                                onClick = { customerMode = CustomerAckMode.SIGN },
                                modifier = Modifier.weight(1f),
                                shape = RoundedCornerShape(8.dp),
                                border = ButtonDefaults.outlinedButtonBorder.copy(
                                    brush = androidx.compose.ui.graphics.SolidColor(BrandLightGray)
                                )
                            ) { 
                                Text(
                                    "Sign on Screen",
                                    fontFamily = LeagueSpartanFamily,
                                    fontWeight = FontWeight.Bold,
                                    color = BrandNavy
                                ) 
                            }
                            OutlinedButton(
                                onClick = { customerMode = CustomerAckMode.PHOTO },
                                modifier = Modifier.weight(1f),
                                shape = RoundedCornerShape(8.dp),
                                border = ButtonDefaults.outlinedButtonBorder.copy(
                                    brush = androidx.compose.ui.graphics.SolidColor(BrandLightGray)
                                )
                            ) { 
                                Text(
                                    "Upload Photo",
                                    fontFamily = LeagueSpartanFamily,
                                    fontWeight = FontWeight.Bold,
                                    color = BrandNavy
                                ) 
                            }
                        }
                    } else {
                        Spacer(modifier = Modifier.height(8.dp))
                        when (customerMode) {
                            CustomerAckMode.SIGN -> {
                                OutlinedButton(
                                    onClick = { 
                                        customerSignatureState.clear()
                                        isSigningCustomer = true 
                                    },
                                    modifier = Modifier.fillMaxWidth(),
                                    shape = RoundedCornerShape(8.dp),
                                    border = ButtonDefaults.outlinedButtonBorder.copy(
                                        brush = androidx.compose.ui.graphics.SolidColor(BrandLightGray)
                                    )
                                ) {
                                    Text(
                                        "DRAW CUSTOMER SIGNATURE",
                                        fontFamily = LeagueSpartanFamily,
                                        fontWeight = FontWeight.Bold,
                                        color = BrandNavy
                                    )
                                }
                            }
                            CustomerAckMode.PHOTO -> {
                                Text(
                                    text = if (customerPhotoUri != null) "Photo selected ✓" else "No photo selected yet",
                                    fontFamily = LibreBaskervilleFamily,
                                    fontSize = 13.sp,
                                    color = TextSecondary
                                )
                                Spacer(modifier = Modifier.height(8.dp))
                                OutlinedButton(
                                    onClick = photoPicker,
                                    shape = RoundedCornerShape(8.dp)
                                ) {
                                    Text(
                                        if (customerPhotoUri != null) "Choose a different photo" else "Choose Photo",
                                        fontFamily = LeagueSpartanFamily,
                                        fontWeight = FontWeight.Bold,
                                        color = BrandNavy
                                    )
                                }
                            }
                            null -> {}
                        }
                        Spacer(modifier = Modifier.height(4.dp))
                        TextButton(onClick = { 
                            customerMode = null
                            customerPhotoUri = null
                            customerSavedBitmap = null
                            customerSignatureState.clear() 
                        }) {
                            Text(
                                "Change method",
                                fontFamily = LeagueSpartanFamily,
                                fontWeight = FontWeight.Bold,
                                fontSize = 12.sp,
                                color = BrandNavy
                            )
                        }
                    }

                    Spacer(modifier = Modifier.height(20.dp))

                    Button(
                        onClick = {
                            coroutineScope.launch {
                                var allOk = true

                                if (employeeSavedBitmap != null || !employeeSignatureState.isEmpty) {
                                    val bytes = employeeSignatureState.toPngBytes(600, 200)
                                    val ok = if (existingEmployee != null && redoEmployee) {
                                        viewModel.replaceSignatureAwait(visitId, existingEmployee.id, bytes, "SIGNATURE")
                                    } else {
                                        viewModel.uploadSignatureAwait(visitId, "EMPLOYEE", bytes, "SIGNATURE")
                                    }
                                    allOk = ok && allOk
                                }

                                if (customerSavedBitmap != null || (!customerSignatureState.isEmpty && customerMode == CustomerAckMode.SIGN)) {
                                    val bytes = customerSignatureState.toPngBytes(600, 200)
                                    val ok = if (existingCustomer != null && redoCustomer) {
                                        viewModel.replaceSignatureAwait(visitId, existingCustomer.id, bytes, "SIGNATURE")
                                    } else {
                                        viewModel.uploadSignatureAwait(visitId, "CUSTOMER", bytes, "SIGNATURE")
                                    }
                                    allOk = ok && allOk
                                } else if (customerMode == CustomerAckMode.PHOTO && customerPhotoUri != null) {
                                    customerPhotoUri?.let { uri ->
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
                                }

                                if (allOk) onComplete()
                            }
                        },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(52.dp),
                        shape = RoundedCornerShape(10.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = BrandNavy,
                            contentColor = BrandWhite
                        ),
                        enabled = state !is SignatureState.Loading
                    ) {
                        if (state is SignatureState.Loading) {
                            CircularProgressIndicator(color = BrandGold, modifier = Modifier.size(24.dp))
                        } else {
                            Text(
                                "SUBMIT SIGN-OFF & COMPLETE",
                                fontFamily = LeagueSpartanFamily,
                                fontWeight = FontWeight.Bold,
                                fontSize = 14.sp,
                                letterSpacing = 0.5.sp,
                                color = BrandWhite
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun CapturedSummaryCard(
    title: String, 
    savedBitmap: Bitmap? = null,
    isAlreadyUploaded: Boolean = false,
    onRedo: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .border(1.dp, BrandLightGray, RoundedCornerShape(10.dp)),
        shape = RoundedCornerShape(10.dp),
        colors = CardDefaults.cardColors(containerColor = BrandWhite)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = title, 
                    fontFamily = LeagueSpartanFamily,
                    fontSize = 13.sp, 
                    fontWeight = FontWeight.Bold,
                    color = BrandNavy, 
                    modifier = Modifier.weight(1f)
                )
                TextButton(onClick = onRedo) { 
                    Text(
                        "CLEAR / RE-SIGN",
                        fontFamily = LeagueSpartanFamily,
                        color = BrandGold,
                        fontWeight = FontWeight.Bold,
                        fontSize = 12.sp
                    ) 
                }
            }

            Spacer(modifier = Modifier.height(6.dp))

            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(100.dp)
                    .background(BrandWhite, RoundedCornerShape(8.dp))
                    .border(1.dp, BrandLightGray, RoundedCornerShape(8.dp))
                    .padding(8.dp),
                contentAlignment = Alignment.Center
            ) {
                if (savedBitmap != null) {
                    Image(
                        bitmap = savedBitmap.asImageBitmap(),
                        contentDescription = "Captured Signature Preview",
                        modifier = Modifier.fillMaxSize(),
                        contentScale = ContentScale.Fit
                    )
                } else if (isAlreadyUploaded) {
                    Text(
                        text = "Signature recorded and verified on server ✓",
                        fontFamily = LibreBaskervilleFamily,
                        color = SuccessGreen,
                        fontSize = 12.sp
                    )
                } else {
                    Text(
                        text = "No signature preview available",
                        fontFamily = LibreBaskervilleFamily,
                        color = TextSecondary,
                        fontSize = 12.sp
                    )
                }
            }
        }
    }
}

@Composable
private fun FullScreenSignatureCapture(
    title: String,
    state: SignatureCaptureState,
    onSave: () -> Unit,
    onClear: () -> Unit,
    onCancel: () -> Unit
) {
    var errorText by remember { mutableStateOf<String?>(null) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(SurfaceSecondary)
            .padding(16.dp)
    ) {
        Text(
            text = title,
            fontFamily = LeagueSpartanFamily,
            fontSize = 20.sp,
            fontWeight = FontWeight.Bold,
            color = BrandNavy
        )
        Text(
            text = "Draw signature authorization clearly below using your finger",
            fontFamily = LibreBaskervilleFamily,
            fontSize = 13.sp,
            color = TextSecondary
        )
        Spacer(modifier = Modifier.height(14.dp))

        if (errorText != null) {
            ErrorBanner(message = errorText!!)
            Spacer(modifier = Modifier.height(10.dp))
        }
        
        SignatureCaptureCanvas(
            state = state,
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f)
        )
        
        Spacer(modifier = Modifier.height(16.dp))
        
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            OutlinedButton(
                onClick = {
                    errorText = null
                    onClear()
                },
                shape = RoundedCornerShape(10.dp),
                border = ButtonDefaults.outlinedButtonBorder.copy(
                    brush = androidx.compose.ui.graphics.SolidColor(BrandLightGray)
                ),
                modifier = Modifier.weight(1f)
            ) {
                Text(
                    "CLEAR",
                    fontFamily = LeagueSpartanFamily,
                    fontWeight = FontWeight.Bold,
                    color = BrandNavy
                )
            }
            Button(
                onClick = {
                    if (!state.hasMeaningfulContent()) {
                        errorText = "Please draw a valid signature before saving."
                        return@Button
                    }
                    errorText = null
                    onSave()
                },
                shape = RoundedCornerShape(10.dp),
                modifier = Modifier.weight(1f),
                colors = ButtonDefaults.buttonColors(
                    containerColor = BrandNavy,
                    contentColor = BrandWhite
                )
            ) {
                Text(
                    "SAVE SIGNATURE",
                    fontFamily = LeagueSpartanFamily,
                    fontWeight = FontWeight.Bold,
                    color = BrandWhite
                )
            }
        }
        
        Spacer(modifier = Modifier.height(8.dp))
        
        TextButton(
            onClick = onCancel,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(
                "Cancel",
                fontFamily = LeagueSpartanFamily,
                fontWeight = FontWeight.Bold,
                color = ErrorRed
            )
        }
    }
}
