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
import androidx.compose.material.icons.filled.CheckCircle
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
import com.fieldtrackpro.android.ui.viewmodel.CheckOutState
import com.fieldtrackpro.android.ui.viewmodel.CheckOutViewModel
import com.fieldtrackpro.android.utils.CoordinateValidator

@Composable
fun CheckOutScreen(
    visitId: String,
    customerId: String,
    viewModel: CheckOutViewModel,
    onNavigateBack: () -> Unit,
    onSuccess: () -> Unit
) {
    val state by viewModel.state.collectAsState()

    var latText by remember { mutableStateOf("") }
    var lonText by remember { mutableStateOf("") }
    var capturedAccuracyM by remember { mutableStateOf<Double?>(null) }
    var capturedIsMock by remember { mutableStateOf(false) }
    var capturedAtMillis by remember { mutableStateOf<Long?>(null) }
    var notes by remember { mutableStateOf("") }
    var isOfflineMode by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        viewModel.resetState()
    }

    if (state is CheckOutState.ActionSuccess) {
        LaunchedEffect(state) {
            viewModel.resetState()
            onSuccess()
        }
    }

    Scaffold(
        topBar = {
            FieldTrackTopAppBar(
                title = "Check-Out & Completion",
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
                        text = "Complete Visit & Check-Out",
                        fontFamily = LeagueSpartanFamily,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold,
                        color = BrandNavy
                    )
                    Text(
                        text = "Capture concluding GPS coordinates and attach optional visit completion notes.",
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

                    if (state is CheckOutState.Error) {
                        ErrorBanner(message = (state as CheckOutState.Error).message)
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    if (state is CheckOutState.InvalidCoordinates) {
                        ErrorBanner(message = (state as CheckOutState.InvalidCoordinates).message)
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    if (state is CheckOutState.GeoRejected) {
                        ErrorBanner(message = (state as CheckOutState.GeoRejected).message)
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    if (state is CheckOutState.LowAccuracy) {
                        ErrorBanner(message = (state as CheckOutState.LowAccuracy).message)
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    if (state is CheckOutState.StaleLocation) {
                        ErrorBanner(message = (state as CheckOutState.StaleLocation).message)
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    if (state is CheckOutState.Conflict) {
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
                                    text = (state as CheckOutState.Conflict).message,
                                    fontFamily = LibreBaskervilleFamily,
                                    fontSize = 12.sp,
                                    color = TextPrimary
                                )
                            }
                        }
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    if (state is CheckOutState.Queued) {
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
                                    text = (state as CheckOutState.Queued).message,
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

                    Spacer(modifier = Modifier.height(10.dp))

                    OutlinedTextField(
                        value = notes,
                        onValueChange = { notes = it },
                        label = { 
                            Text(
                                "Visit Outcome Notes (Optional)",
                                fontFamily = LeagueSpartanFamily,
                                fontWeight = FontWeight.SemiBold
                            ) 
                        },
                        placeholder = { Text("Enter discussion summary, follow-up items...", color = TextSecondary) },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(100.dp),
                        maxLines = 4,
                        shape = RoundedCornerShape(10.dp),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedTextColor = TextPrimary,
                            unfocusedTextColor = TextPrimary,
                            focusedBorderColor = BrandGold,
                            unfocusedBorderColor = BrandLightGray,
                            focusedContainerColor = BrandWhite,
                            unfocusedContainerColor = BrandWhite
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

                    val parsedLat = CoordinateValidator.parseCoordinate(latText)
                    val parsedLon = CoordinateValidator.parseCoordinate(lonText)
                    val canSubmit = CoordinateValidator.isValidCoordinate(parsedLat, parsedLon) && state !is CheckOutState.Processing

                    Button(
                        onClick = {
                            if (parsedLat != null && parsedLon != null) {
                                val acc = capturedAccuracyM ?: 10.0
                                val isMock = capturedIsMock
                                val ts = capturedAtMillis ?: System.currentTimeMillis()

                                viewModel.executeCheckOut(
                                    visitId = visitId,
                                    lat = parsedLat,
                                    lon = parsedLon,
                                    notes = notes.ifBlank { null },
                                    accuracyM = acc,
                                    isMock = isMock,
                                    capturedAtMillis = ts,
                                    isOfflineMode = isOfflineMode
                                )
                            }
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
                        if (state is CheckOutState.Processing) {
                            CircularProgressIndicator(color = BrandGold, modifier = Modifier.size(24.dp))
                        } else {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(
                                    imageVector = Icons.Default.CheckCircle,
                                    contentDescription = null,
                                    tint = if (canSubmit) BrandGold else TextSecondary,
                                    modifier = Modifier.size(20.dp)
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                                Text(
                                    "COMPLETE VISIT & CHECK-OUT",
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
