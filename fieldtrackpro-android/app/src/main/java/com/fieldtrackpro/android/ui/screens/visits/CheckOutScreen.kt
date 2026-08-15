package com.fieldtrackpro.android.ui.screens.visits

import androidx.compose.foundation.background
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
fun CheckOutScreen(
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
    var notes by remember { mutableStateOf("") }
    var isOfflineMode by remember { mutableStateOf(false) }

    if (state is CheckInState.ActionSuccess) {
        onSuccess()
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
                        text = "Complete Visit & Record Location",
                        style = MaterialTheme.typography.titleLarge,
                        color = FieldTrackNavy
                    )
                    Text(
                        text = "Provide mandatory check-out coordinates and visit notes.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TextMuted
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

                    // P0-4: read-only, populated only by the capture button
                    // above - see the identical rationale in CheckInScreen.
                    OutlinedTextField(
                        value = latText,
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Check-Out Latitude") },
                        placeholder = { Text("Capture your location above") },
                        modifier = Modifier.fillMaxWidth()
                    )

                    Spacer(modifier = Modifier.height(10.dp))

                    OutlinedTextField(
                        value = lonText,
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Check-Out Longitude") },
                        placeholder = { Text("Capture your location above") },
                        modifier = Modifier.fillMaxWidth()
                    )

                    Spacer(modifier = Modifier.height(10.dp))

                    OutlinedTextField(
                        value = notes,
                        onValueChange = { notes = it },
                        label = { Text("Visit Notes & Summary") },
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

                    val parsedLat = latText.toDoubleOrNull()
                    val parsedLon = lonText.toDoubleOrNull()
                    val isNotNullIsland = parsedLat != 0.0 || parsedLon != 0.0
                    val hasValidCoordinates = parsedLat != null && parsedLon != null &&
                        parsedLat in -90.0..90.0 && parsedLon in -180.0..180.0 && isNotNullIsland
                    // P0-4: a real GPS fix must have been captured.
                    val hasRealCapture = hasValidCoordinates && capturedAccuracyM != null && capturedAtMillis != null

                    Button(
                        onClick = {
                            if (parsedLat != null && parsedLon != null && capturedAtMillis != null) {
                                viewModel.executeCheckOut(
                                    visitId, parsedLat, parsedLon,
                                    notes = notes,
                                    capturedAtMillis = capturedAtMillis!!,
                                    accuracyM = capturedAccuracyM,
                                    isMock = capturedIsMock,
                                    isOfflineMode = isOfflineMode,
                                )
                            }
                        },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(50.dp),
                        shape = RoundedCornerShape(8.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = SuccessGreen,
                            contentColor = SurfaceWhite
                        ),
                        enabled = hasRealCapture && state !is CheckInState.Processing
                    ) {
                        if (state is CheckInState.Processing) {
                            CircularProgressIndicator(color = SurfaceWhite, modifier = Modifier.height(24.dp))
                        } else {
                            Text("SUBMIT CHECK-OUT & CLOSE VISIT", fontSize = 15.sp, fontWeight = FontWeight.Bold, color = SurfaceWhite)
                        }
                    }
                }
            }
        }
    }
}
