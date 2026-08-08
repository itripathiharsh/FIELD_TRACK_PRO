package com.fieldtrackpro.android.ui.screens.signature

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
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
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.ui.components.ErrorBanner
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.theme.CoralRed
import com.fieldtrackpro.android.ui.theme.ElectricBlue
import com.fieldtrackpro.android.ui.theme.Slate50
import com.fieldtrackpro.android.ui.theme.Slate500
import com.fieldtrackpro.android.ui.theme.Slate900
import com.fieldtrackpro.android.ui.theme.SurfaceWhite
import com.fieldtrackpro.android.ui.viewmodel.SignatureState
import com.fieldtrackpro.android.ui.viewmodel.SignatureViewModel

@Composable
fun SignatureScreen(
    visitId: String,
    viewModel: SignatureViewModel,
    onNavigateBack: () -> Unit,
    onComplete: () -> Unit
) {
    val state by viewModel.signatureState.collectAsState()
    val employeeSignatureState = rememberSignatureCaptureState()
    val customerSignatureState = rememberSignatureCaptureState()

    LaunchedEffect(visitId) {
        viewModel.loadVisitSignatures(visitId)
    }

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
                .background(Slate50)
                .padding(innerPadding)
                .padding(20.dp)
        ) {
            Text(
                text = "Visit Completion",
                fontSize = 18.sp,
                fontWeight = FontWeight.Bold,
                color = Slate900
            )
            Text(
                text = "Capture employee and customer signatures to complete this visit.",
                fontSize = 13.sp,
                color = Slate500
            )

            Spacer(modifier = Modifier.height(16.dp))

            if (state is SignatureState.Error) {
                ErrorBanner(message = (state as SignatureState.Error).message)
                Spacer(modifier = Modifier.height(12.dp))
            }

            if (state is SignatureState.UploadSuccess) {
                Text(
                    text = "Signature saved!",
                    fontSize = 13.sp,
                    color = ElectricBlue,
                    fontWeight = FontWeight.Bold
                )
                Spacer(modifier = Modifier.height(12.dp))
            }

            SignatureCaptureSection(
                title = "Employee Signature",
                state = employeeSignatureState,
                onClear = { employeeSignatureState.clear() }
            )

            Spacer(modifier = Modifier.height(16.dp))

            SignatureCaptureSection(
                title = "Customer Signature",
                state = customerSignatureState,
                onClear = { customerSignatureState.clear() }
            )

            Spacer(modifier = Modifier.height(24.dp))

            Button(
                onClick = {
                    // Upload both signatures
                    if (!employeeSignatureState.isEmpty) {
                        val base64 = employeeSignatureState.toBase64Png(600, 200)
                        viewModel.uploadSignature(visitId, "EMPLOYEE", base64)
                    }
                    if (!customerSignatureState.isEmpty) {
                        val base64 = customerSignatureState.toBase64Png(600, 200)
                        viewModel.uploadSignature(visitId, "CUSTOMER", base64)
                    }
                    onComplete()
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(50.dp),
                shape = RoundedCornerShape(8.dp),
                colors = ButtonDefaults.buttonColors(containerColor = ElectricBlue),
                enabled = !employeeSignatureState.isEmpty && !customerSignatureState.isEmpty && state !is SignatureState.Loading
            ) {
                Text("SUBMIT SIGNATURES", fontWeight = FontWeight.Bold)
            }

            Spacer(modifier = Modifier.height(8.dp))

            Button(
                onClick = onNavigateBack,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(50.dp),
                shape = RoundedCornerShape(8.dp),
                colors = ButtonDefaults.buttonColors(containerColor = CoralRed)
            ) {
                Text("CANCEL", fontWeight = FontWeight.Bold)
            }
        }
    }
}
