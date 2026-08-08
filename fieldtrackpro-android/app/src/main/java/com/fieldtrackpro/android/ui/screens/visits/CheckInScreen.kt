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
import com.fieldtrackpro.android.ui.theme.ElectricBlue
import com.fieldtrackpro.android.ui.theme.EmeraldGreen
import com.fieldtrackpro.android.ui.theme.Slate50
import com.fieldtrackpro.android.ui.theme.Slate500
import com.fieldtrackpro.android.ui.theme.Slate900
import com.fieldtrackpro.android.ui.theme.SurfaceWhite
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
                .background(Slate50)
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
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold,
                        color = Slate900
                    )
                    Text(
                        text = "Server verifies geofence proximity (100m) and GPS accuracy.",
                        fontSize = 13.sp,
                        color = Slate500
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    if (state is CheckInState.Error) {
                        ErrorBanner(message = (state as CheckInState.Error).message)
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    if (state is CheckInState.VerifySuccess) {
                        val ver = (state as CheckInState.VerifySuccess).verify
                        Card(
                            modifier = Modifier.fillMaxWidth(),
                            colors = CardDefaults.cardColors(
                                containerColor = if (ver.isValid) EmeraldGreen.copy(alpha = 0.15f) else Slate50
                            )
                        ) {
                            Column(modifier = Modifier.padding(12.dp)) {
                                Text(
                                    text = if (ver.isValid) "PROXIMITY VERIFIED PASS" else "OUTSIDE GEOFENCE RADIUS",
                                    fontSize = 13.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = if (ver.isValid) EmeraldGreen else Slate900
                                )
                                Text(
                                    text = "Distance to customer: ${String.format("%.1f", ver.distanceM)}m (Max allowed: ${ver.geofenceRadiusM}m)",
                                    fontSize = 12.sp
                                )
                            }
                        }
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    OutlinedTextField(
                        value = latText,
                        onValueChange = { latText = it },
                        label = { Text("Latitude") },
                        modifier = Modifier.fillMaxWidth()
                    )

                    Spacer(modifier = Modifier.height(10.dp))

                    OutlinedTextField(
                        value = lonText,
                        onValueChange = { lonText = it },
                        label = { Text("Longitude") },
                        modifier = Modifier.fillMaxWidth()
                    )

                    Spacer(modifier = Modifier.height(12.dp))

                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(
                            checked = isOfflineMode,
                            onCheckedChange = { isOfflineMode = it }
                        )
                        Spacer(modifier = Modifier.width(6.dp))
                        Text(text = "Simulate Offline Mode (Enqueue Action)", fontSize = 13.sp, color = Slate900)
                    }

                    Spacer(modifier = Modifier.height(20.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        // FT-070: coordinates are parsed once, and an
                        // unparseable value yields null rather than 0.0.
                        // Defaulting to (0,0) is the same defect as FT-004 on
                        // the server: it silently relocates the check-in to
                        // Null Island instead of refusing to submit.
                        val parsedLat = latText.toDoubleOrNull()
                        val parsedLon = lonText.toDoubleOrNull()
                        val isNotNullIsland = parsedLat != 0.0 || parsedLon != 0.0
                        val hasValidCoordinates = parsedLat != null && parsedLon != null &&
                            parsedLat in -90.0..90.0 && parsedLon in -180.0..180.0 && isNotNullIsland

                        OutlinedButton(
                            onClick = {
                                if (parsedLat != null && parsedLon != null) {
                                    viewModel.verifyLocationPreflight(customerId, parsedLat, parsedLon)
                                }
                            },
                            enabled = hasValidCoordinates,
                            modifier = Modifier.weight(1f)
                        ) {
                            Text("PRE-CHECK GPS")
                        }

                        Button(
                            onClick = {
                                if (parsedLat != null && parsedLon != null) {
                                    viewModel.executeCheckIn(
                                        visitId, parsedLat, parsedLon, isOfflineMode = isOfflineMode
                                    )
                                }
                            },
                            modifier = Modifier.weight(1f),
                            colors = ButtonDefaults.buttonColors(containerColor = ElectricBlue),
                            enabled = hasValidCoordinates && state !is CheckInState.Processing
                        ) {
                            if (state is CheckInState.Processing) {
                                CircularProgressIndicator(color = SurfaceWhite, modifier = Modifier.height(20.dp))
                            } else {
                                Text("SUBMIT CHECK-IN")
                            }
                        }
                    }
                }
            }
        }
    }
}

