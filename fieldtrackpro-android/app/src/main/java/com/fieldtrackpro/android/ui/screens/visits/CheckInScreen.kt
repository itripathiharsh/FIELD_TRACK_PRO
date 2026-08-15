package com.fieldtrackpro.android.ui.screens.visits

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
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
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.ui.components.ErrorBanner
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.components.LocationCaptureButton
import com.fieldtrackpro.android.ui.theme.FieldTrackAmber
import com.fieldtrackpro.android.ui.theme.FieldTrackNavy
import com.fieldtrackpro.android.ui.theme.SuccessGreen
import com.fieldtrackpro.android.ui.theme.SurfaceOffWhite
import com.fieldtrackpro.android.ui.theme.SurfaceWhite
import com.fieldtrackpro.android.ui.theme.TextMuted
import com.fieldtrackpro.android.ui.theme.TextPrimary
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

    if (state is CheckInState.ActionSuccess) {
        onSuccess()
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
                .background(SurfaceOffWhite)
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
                        text = "GPS Coordinate Verification",
                        style = MaterialTheme.typography.titleLarge,
                        color = FieldTrackNavy
                    )
                    Text(
                        text = "Server verifies proximity against the customer's configured geofence radius and GPS accuracy.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TextMuted
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

                    // Saved offline and will sync automatically once the
                    // device has connectivity - distinct from a real
                    // rejection so the rep isn't alarmed by a red error for
                    // something that isn't actually a problem.
                    if (state is CheckInState.Queued) {
                        Text(
                            text = "Queued for automatic sync - will confirm once connection improves.",
                            fontSize = 13.sp,
                            color = FieldTrackAmber,
                            fontWeight = FontWeight.Bold
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    if (state is CheckInState.VerifySuccess) {
                        val ver = (state as CheckInState.VerifySuccess).verify
                        Card(
                            modifier = Modifier.fillMaxWidth(),
                            colors = CardDefaults.cardColors(
                                containerColor = if (ver.isValid) SuccessGreen.copy(alpha = 0.15f) else SurfaceOffWhite
                            )
                        ) {
                            Column(modifier = Modifier.padding(12.dp)) {
                                Text(
                                    text = if (ver.isValid) "PROXIMITY VERIFIED PASS" else "OUTSIDE GEOFENCE RADIUS",
                                    fontSize = 13.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = if (ver.isValid) SuccessGreen else TextPrimary
                                )
                                Text(
                                    text = "Distance to customer: ${String.format("%.1f", ver.distanceM)}m (Max allowed: ${ver.geofenceRadiusM}m)",
                                    fontSize = 12.sp,
                                    color = TextMuted
                                )
                            }
                        }
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    // P0-4: read-only. These fields exist so the rep can see
                    // exactly what will be submitted, not to let anyone type
                    // in arbitrary coordinates as a substitute for a real GPS
                    // fix - the only way to populate them is the capture
                    // button above, which is the only path that also sets a
                    // real accuracy/mock-provider signal. The submit button
                    // below is disabled until that has happened.
                    OutlinedTextField(
                        value = latText,
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Latitude") },
                        placeholder = { Text("Capture your location above") },
                        modifier = Modifier.fillMaxWidth()
                    )

                    Spacer(modifier = Modifier.height(10.dp))

                    OutlinedTextField(
                        value = lonText,
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Longitude") },
                        placeholder = { Text("Capture your location above") },
                        modifier = Modifier.fillMaxWidth()
                    )

                    Spacer(modifier = Modifier.height(12.dp))

                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(
                            checked = isOfflineMode,
                            onCheckedChange = { isOfflineMode = it }
                        )
                        Spacer(modifier = Modifier.width(6.dp))
                        Text(text = "Simulate Offline Mode (Enqueue Action)", fontSize = 13.sp, color = TextPrimary)
                    }

                    Spacer(modifier = Modifier.height(20.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        val parsedLat = latText.toDoubleOrNull()
                        val parsedLon = lonText.toDoubleOrNull()
                        val isNotNullIsland = parsedLat != 0.0 || parsedLon != 0.0
                        val hasValidCoordinates = parsedLat != null && parsedLon != null &&
                            parsedLat in -90.0..90.0 && parsedLon in -180.0..180.0 && isNotNullIsland
                        // P0-4: a real GPS fix must have been captured - the
                        // fields are read-only, but this is the explicit gate
                        // that actually enables submission on it.
                        val hasRealCapture = hasValidCoordinates && capturedAccuracyM != null && capturedAtMillis != null

                        OutlinedButton(
                            onClick = {
                                if (parsedLat != null && parsedLon != null) {
                                    viewModel.verifyLocationPreflight(customerId, parsedLat, parsedLon)
                                }
                            },
                            enabled = hasRealCapture,
                            modifier = Modifier.weight(1f)
                        ) {
                            Text("PRE-CHECK GPS", color = FieldTrackNavy)
                        }

                        Button(
                            onClick = {
                                if (parsedLat != null && parsedLon != null && capturedAtMillis != null) {
                                    viewModel.executeCheckIn(
                                        visitId, parsedLat, parsedLon,
                                        capturedAtMillis = capturedAtMillis!!,
                                        accuracyM = capturedAccuracyM,
                                        isMock = capturedIsMock,
                                        isOfflineMode = isOfflineMode,
                                    )
                                }
                            },
                            modifier = Modifier.weight(1f),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = FieldTrackNavy,
                                contentColor = SurfaceWhite
                            ),
                            enabled = hasRealCapture && state !is CheckInState.Processing
                        ) {
                            if (state is CheckInState.Processing) {
                                CircularProgressIndicator(color = SurfaceWhite, modifier = Modifier.height(20.dp))
                            } else {
                                Text("SUBMIT CHECK-IN", color = SurfaceWhite)
                            }
                        }
                    }
                }
            }
        }
    }
}
