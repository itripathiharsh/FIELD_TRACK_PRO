package com.fieldtrackpro.android.ui.screens.visits

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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.ui.components.ErrorBanner
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.components.LocationCaptureButton
import com.fieldtrackpro.android.ui.theme.BrandBlack
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandLightGray
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.theme.LibreBaskervilleFamily
import com.fieldtrackpro.android.ui.theme.SuccessGreen
import com.fieldtrackpro.android.ui.theme.SurfaceSecondary
import com.fieldtrackpro.android.ui.theme.TextPrimary
import com.fieldtrackpro.android.ui.theme.TextSecondary
import com.fieldtrackpro.android.ui.viewmodel.CheckInState
import com.fieldtrackpro.android.ui.viewmodel.CheckInViewModel

@Composable
fun CheckInScreen(
    visitId: String,
    customerId: String,
    viewModel: CheckInViewModel,
    onNavigateBack: () -> Unit,
    onSuccess: () -> Unit
) {
    val state by viewModel.state.collectAsState()

    var latText by remember { mutableStateOf("") }
    var lonText by remember { mutableStateOf("") }
    var capturedAccuracyM by remember { mutableStateOf<Double?>(null) }
    var capturedIsMock by remember { mutableStateOf(false) }
    var capturedAtMillis by remember { mutableStateOf<Long?>(null) }
    var isOfflineMode by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        viewModel.resetState()
    }

    if (state is CheckInState.ActionSuccess) {
        LaunchedEffect(state) {
            viewModel.resetState()
            onSuccess()
        }
    }

    Scaffold(
        topBar = {
            FieldTrackTopAppBar(
                title = "Check-In Geo Verification",
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
                        text = "GPS Coordinate Verification",
                        fontFamily = LeagueSpartanFamily,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold,
                        color = BrandNavy
                    )
                    Text(
                        text = "Server verifies proximity against the customer's configured geofence radius and GPS accuracy.",
                        fontFamily = LibreBaskervilleFamily,
                        fontSize = 13.sp,
                        color = TextSecondary
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    LocationCaptureButton(
                        onCaptured = { result ->
                            latText = result.latitude.toString()
                            lonText = result.longitude.toString()
                            capturedAccuracyM = result.accuracy.toDouble()
                            capturedIsMock = result.isMockLocation
                            capturedAtMillis = result.timestamp
                        }
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    if (state is CheckInState.Error) {
                        ErrorBanner(message = (state as CheckInState.Error).message)
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    if (state is CheckInState.GeoRejected) {
                        ErrorBanner(message = (state as CheckInState.GeoRejected).message)
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    if (state is CheckInState.LowAccuracy) {
                        ErrorBanner(message = (state as CheckInState.LowAccuracy).message)
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    if (state is CheckInState.StaleLocation) {
                        ErrorBanner(message = (state as CheckInState.StaleLocation).message)
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    if (state is CheckInState.Conflict) {
                        Card(
                            modifier = Modifier
                                .fillMaxWidth()
                                .border(1.dp, BrandGold, RoundedCornerShape(8.dp)),
                            shape = RoundedCornerShape(8.dp),
                            colors = CardDefaults.cardColors(containerColor = BrandGold.copy(alpha = 0.12f))
                        ) {
                            Column(modifier = Modifier.padding(12.dp)) {
                                Text(
                                    text = "SCHEDULE CONFLICT",
                                    fontFamily = LeagueSpartanFamily,
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.Bold,
                                    letterSpacing = 0.5.sp,
                                    color = BrandNavy
                                )
                                Text(
                                    text = (state as CheckInState.Conflict).message,
                                    fontFamily = LibreBaskervilleFamily,
                                    fontSize = 12.sp,
                                    color = TextPrimary
                                )
                            }
                        }
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    if (state is CheckInState.Queued) {
                        Card(
                            modifier = Modifier
                                .fillMaxWidth()
                                .border(1.dp, BrandGold, RoundedCornerShape(8.dp)),
                            shape = RoundedCornerShape(8.dp),
                            colors = CardDefaults.cardColors(containerColor = BrandGold.copy(alpha = 0.12f))
                        ) {
                            Column(modifier = Modifier.padding(12.dp)) {
                                Text(
                                    text = "QUEUED FOR SYNC",
                                    fontFamily = LeagueSpartanFamily,
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.Bold,
                                    letterSpacing = 0.5.sp,
                                    color = BrandNavy
                                )
                                Text(
                                    text = (state as CheckInState.Queued).message,
                                    fontFamily = LibreBaskervilleFamily,
                                    fontSize = 12.sp,
                                    color = TextPrimary
                                )
                            }
                        }
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    if (state is CheckInState.VerifySuccess) {
                        val ver = (state as CheckInState.VerifySuccess).verify
                        Card(
                            modifier = Modifier
                                .fillMaxWidth()
                                .border(
                                    1.dp,
                                    if (ver.isValid) SuccessGreen else BrandGold,
                                    RoundedCornerShape(8.dp)
                                ),
                            shape = RoundedCornerShape(8.dp),
                            colors = CardDefaults.cardColors(
                                containerColor = if (ver.isValid) SuccessGreen.copy(alpha = 0.12f) else BrandGold.copy(alpha = 0.12f)
                            )
                        ) {
                            Column(modifier = Modifier.padding(12.dp)) {
                                Text(
                                    text = if (ver.isValid) "PROXIMITY VERIFIED PASS" else "OUTSIDE GEOFENCE RADIUS",
                                    fontFamily = LeagueSpartanFamily,
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.Bold,
                                    letterSpacing = 0.5.sp,
                                    color = if (ver.isValid) SuccessGreen else BrandNavy
                                )
                                Text(
                                    text = "Distance to customer: ${String.format("%.1f", ver.distanceM)}m (Max allowed: ${ver.geofenceRadiusM}m)",
                                    fontFamily = LibreBaskervilleFamily,
                                    fontSize = 12.sp,
                                    color = TextPrimary
                                )
                            }
                        }
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    OutlinedTextField(
                        value = latText,
                        onValueChange = {},
                        readOnly = true,
                        label = { 
                            Text(
                                "Latitude",
                                fontFamily = LeagueSpartanFamily,
                                fontWeight = FontWeight.SemiBold
                            ) 
                        },
                        placeholder = { Text("Capture your location above", color = TextSecondary) },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(10.dp),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedTextColor = TextPrimary,
                            unfocusedTextColor = TextPrimary,
                            focusedBorderColor = BrandGold,
                            unfocusedBorderColor = BrandLightGray,
                            focusedContainerColor = SurfaceSecondary,
                            unfocusedContainerColor = SurfaceSecondary
                        )
                    )

                    Spacer(modifier = Modifier.height(10.dp))

                    OutlinedTextField(
                        value = lonText,
                        onValueChange = {},
                        readOnly = true,
                        label = { 
                            Text(
                                "Longitude",
                                fontFamily = LeagueSpartanFamily,
                                fontWeight = FontWeight.SemiBold
                            ) 
                        },
                        placeholder = { Text("Capture your location above", color = TextSecondary) },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(10.dp),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedTextColor = TextPrimary,
                            unfocusedTextColor = TextPrimary,
                            focusedBorderColor = BrandGold,
                            unfocusedBorderColor = BrandLightGray,
                            focusedContainerColor = SurfaceSecondary,
                            unfocusedContainerColor = SurfaceSecondary
                        )
                    )

                    Spacer(modifier = Modifier.height(12.dp))

                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(
                            checked = isOfflineMode,
                            onCheckedChange = { isOfflineMode = it },
                            colors = CheckboxDefaults.colors(
                                checkedColor = BrandNavy,
                                checkmarkColor = BrandGold
                            )
                        )
                        Spacer(modifier = Modifier.width(6.dp))
                        Text(
                            text = "Simulate Offline Mode (Enqueue Action)",
                            fontFamily = LeagueSpartanFamily,
                            fontSize = 13.sp,
                            color = TextPrimary
                        )
                    }

                    Spacer(modifier = Modifier.height(16.dp))

                    val canSubmit = latText.isNotBlank() && lonText.isNotBlank() && state !is CheckInState.Processing

                    Button(
                        onClick = {
                            val lat = latText.toDoubleOrNull() ?: 0.0
                            val lon = lonText.toDoubleOrNull() ?: 0.0
                            val acc = capturedAccuracyM ?: 10.0
                            val isMock = capturedIsMock
                            val ts = capturedAtMillis ?: System.currentTimeMillis()

                            viewModel.executeCheckIn(
                                visitId = visitId,
                                lat = lat,
                                lon = lon,
                                accuracyM = acc,
                                isMock = isMock,
                                capturedAtMillis = ts,
                                isOfflineMode = isOfflineMode
                            )
                        },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(52.dp),
                        shape = RoundedCornerShape(10.dp),
                        enabled = canSubmit,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = BrandNavy,
                            contentColor = BrandWhite,
                            disabledContainerColor = BrandLightGray,
                            disabledContentColor = TextSecondary
                        )
                    ) {
                        if (state is CheckInState.Processing) {
                            CircularProgressIndicator(color = BrandGold, modifier = Modifier.size(24.dp))
                        } else {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(
                                    imageVector = Icons.Default.LocationOn,
                                    contentDescription = null,
                                    tint = if (canSubmit) BrandGold else TextSecondary,
                                    modifier = Modifier.size(20.dp)
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                                Text(
                                    "VERIFY & SUBMIT CHECK-IN",
                                    fontFamily = LeagueSpartanFamily,
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 14.sp,
                                    letterSpacing = 0.5.sp,
                                    color = if (canSubmit) BrandWhite else TextSecondary
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}
