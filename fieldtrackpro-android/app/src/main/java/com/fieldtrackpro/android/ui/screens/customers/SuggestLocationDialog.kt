package com.fieldtrackpro.android.ui.screens.customers

import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.MyLocation
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.data.model.LocationProposalCreate
import com.fieldtrackpro.android.data.model.LocationProposalDto
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.CustomerRepository
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.services.LocationCaptureService
import com.fieldtrackpro.android.services.LocationResult
import androidx.compose.foundation.BorderStroke
import androidx.compose.material3.OutlinedTextFieldDefaults
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandGoldLight
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
import com.fieldtrackpro.android.ui.theme.TextSubtle
import kotlinx.coroutines.launch

/**
 * SuggestLocationDialog allows field employees to capture their current GPS coordinates
 * and propose a location update for an existing outlet.
 *
 * CRITICAL RULE: Zero direct coordinate overwrite. Proposal status is PENDING and must be approved by Admin.
 */
@Composable
fun SuggestLocationDialog(
    customerId: String,
    customerName: String,
    currentLatitude: Double?,
    currentLongitude: Double?,
    onDismiss: () -> Unit,
    onProposalSubmitted: (LocationProposalDto) -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val locationService = remember { LocationCaptureService(context) }
    val customerRepository = remember {
        CustomerRepository(ApiClient.createCustomerApi(com.fieldtrackpro.android.data.local.TokenManager(context)))
    }

    var isCapturingLocation by remember { mutableStateOf(false) }
    var locationResult by remember { mutableStateOf<LocationResult?>(null) }
    var locationError by remember { mutableStateOf<String?>(null) }

    var notes by remember { mutableStateOf("") }
    var isSubmitting by remember { mutableStateOf(false) }
    var submitError by remember { mutableStateOf<String?>(null) }

    fun captureLiveGps() {
        if (!locationService.hasLocationPermission()) {
            locationError = "Location permission required. Please grant permission."
            return
        }
        if (!locationService.isLocationEnabled()) {
            locationError = "GPS is turned off. Please enable location services."
            return
        }
        isCapturingLocation = true
        locationError = null
        scope.launch {
            try {
                val loc = locationService.getCurrentLocation()
                locationResult = loc
            } catch (e: Exception) {
                locationError = e.localizedMessage ?: "Failed to acquire GPS fix"
            } finally {
                isCapturingLocation = false
            }
        }
    }

    LaunchedEffect(Unit) {
        captureLiveGps()
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = BrandWhite,
        shape = RoundedCornerShape(16.dp),
        title = {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Box(
                    modifier = Modifier
                        .size(36.dp)
                        .background(BrandGoldLight, androidx.compose.foundation.shape.CircleShape),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        imageVector = Icons.Default.LocationOn,
                        contentDescription = null,
                        tint = BrandNavy,
                        modifier = Modifier.size(20.dp)
                    )
                }
                Column {
                    Text(
                        text = "Suggest Location Update",
                        fontFamily = LibreBaskervilleFamily,
                        fontWeight = FontWeight.Bold,
                        fontSize = 17.sp,
                        color = BrandNavy
                    )
                    Text(
                        text = "Submit GPS coordinates for review",
                        fontFamily = LeagueSpartanFamily,
                        fontSize = 11.sp,
                        color = TextSubtle
                    )
                }
            }
        },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 4.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Text(
                    text = customerName,
                    fontWeight = FontWeight.Bold,
                    fontSize = 14.sp,
                    color = BrandNavy,
                    fontFamily = LeagueSpartanFamily
                )

                // Current Registered Location
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(10.dp))
                        .background(Color(0xFFF6F8FA))
                        .border(1.dp, BrandLightGray, RoundedCornerShape(10.dp))
                        .padding(12.dp)
                ) {
                    Column {
                        Text(
                            text = "CURRENT REGISTERED COORDINATES",
                            fontSize = 10.sp,
                            fontWeight = FontWeight.Bold,
                            color = TextSubtle,
                            fontFamily = LeagueSpartanFamily
                        )
                        Spacer(modifier = Modifier.height(2.dp))
                        if (currentLatitude != null && currentLongitude != null) {
                            Text(
                                text = "%.6f, %.6f".format(currentLatitude, currentLongitude),
                                fontSize = 13.sp,
                                fontWeight = FontWeight.Bold,
                                color = BrandNavy,
                                fontFamily = LeagueSpartanFamily
                            )
                        } else {
                            Text(
                                text = "No location registered yet (PENDING_COORDINATES)",
                                fontSize = 12.sp,
                                color = TextSubtle,
                                fontFamily = LeagueSpartanFamily
                            )
                        }
                    }
                }

                // Proposed Location GPS Capture
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(10.dp))
                        .background(Color(0xFFF6F8FA))
                        .border(1.dp, BrandLightGray, RoundedCornerShape(10.dp))
                        .padding(12.dp)
                ) {
                    Column {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = "YOUR CURRENT GPS FIX",
                                fontSize = 10.sp,
                                fontWeight = FontWeight.Bold,
                                color = TextSubtle,
                                fontFamily = LeagueSpartanFamily
                            )
                            IconButton(
                                onClick = { captureLiveGps() },
                                modifier = Modifier.size(24.dp),
                                enabled = !isCapturingLocation
                            ) {
                                Icon(
                                    imageVector = Icons.Default.Refresh,
                                    contentDescription = "Refresh GPS",
                                    tint = BrandNavy,
                                    modifier = Modifier.size(16.dp)
                                )
                            }
                        }

                        Spacer(modifier = Modifier.height(4.dp))

                        if (isCapturingLocation) {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(16.dp),
                                    color = BrandNavy,
                                    strokeWidth = 2.dp
                                )
                                Text(
                                    text = "Acquiring high-accuracy GPS fix...",
                                    fontSize = 12.sp,
                                    color = TextSubtle,
                                    fontFamily = LeagueSpartanFamily
                                )
                            }
                        } else if (locationResult != null) {
                            val loc = locationResult!!
                            Text(
                                text = "%.6f, %.6f".format(loc.latitude, loc.longitude),
                                fontSize = 13.sp,
                                fontWeight = FontWeight.Bold,
                                color = BrandNavy,
                                fontFamily = LeagueSpartanFamily
                            )
                            Spacer(modifier = Modifier.height(2.dp))
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(
                                    text = "Accuracy: ±%.1fm".format(loc.accuracy),
                                    fontSize = 11.sp,
                                    color = if (loc.accuracy <= 50f) SuccessGreen else BrandGold,
                                    fontWeight = FontWeight.Bold,
                                    fontFamily = LeagueSpartanFamily
                                )
                                if (currentLatitude != null && currentLongitude != null) {
                                    val dist = LocationCaptureService.calculateDistanceM(
                                        currentLatitude, currentLongitude, loc.latitude, loc.longitude
                                    )
                                    Spacer(modifier = Modifier.width(8.dp))
                                    Text(
                                        text = "· Shift: %.0fm".format(dist),
                                        fontSize = 11.sp,
                                        color = TextSubtle,
                                        fontFamily = LeagueSpartanFamily
                                    )
                                }
                            }
                        } else if (locationError != null) {
                            Text(
                                text = locationError!!,
                                fontSize = 12.sp,
                                color = ErrorRed,
                                fontFamily = LeagueSpartanFamily
                            )
                        }
                    }
                }

                // Notes Field
                OutlinedTextField(
                    value = notes,
                    onValueChange = { notes = it },
                    label = { Text("Field Notes / Landmark (Optional)", fontSize = 12.sp, color = TextSubtle) },
                    placeholder = { Text("e.g. Main entrance facing east road", fontSize = 11.sp) },
                    modifier = Modifier.fillMaxWidth(),
                    maxLines = 2,
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = BrandNavy,
                        unfocusedBorderColor = BrandLightGray,
                        focusedLabelColor = BrandNavy,
                        cursorColor = BrandNavy
                    ),
                    shape = RoundedCornerShape(10.dp),
                    textStyle = androidx.compose.ui.text.TextStyle(
                        fontSize = 13.sp,
                        fontFamily = LeagueSpartanFamily,
                        color = BrandNavy
                    )
                )

                // Info banner explaining Admin approval flow
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(8.dp))
                        .background(BrandGoldLight)
                        .padding(10.dp),
                    verticalAlignment = Alignment.Top
                ) {
                    Icon(
                        imageVector = Icons.Default.Info,
                        contentDescription = null,
                        tint = BrandNavy,
                        modifier = Modifier.size(16.dp)
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(
                        text = "Submitted location will be reviewed by Admin before official coordinates are updated.",
                        fontSize = 11.sp,
                        color = BrandNavy,
                        fontFamily = LeagueSpartanFamily,
                        lineHeight = 14.sp
                    )
                }

                if (submitError != null) {
                    Text(
                        text = submitError!!,
                        fontSize = 12.sp,
                        color = ErrorRed,
                        fontFamily = LeagueSpartanFamily
                    )
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    val loc = locationResult
                    if (loc == null) {
                        Toast.makeText(context, "Please wait for GPS fix", Toast.LENGTH_SHORT).show()
                        return@Button
                    }
                    isSubmitting = true
                    submitError = null
                    scope.launch {
                        val proposalReq = LocationProposalCreate(
                            proposedLatitude = loc.latitude,
                            proposedLongitude = loc.longitude,
                            gpsAccuracyMeters = loc.accuracy.toDouble(),
                            notes = notes.trim().ifEmpty { null }
                        )
                        when (val res = customerRepository.proposeCustomerLocation(customerId, proposalReq)) {
                            is Resource.Success -> {
                                Toast.makeText(
                                    context,
                                    "Location update proposed! Awaiting Admin review.",
                                    Toast.LENGTH_LONG
                                ).show()
                                onProposalSubmitted(res.data)
                                onDismiss()
                            }
                            is Resource.Error -> {
                                submitError = res.message
                            }
                            else -> {}
                        }
                        isSubmitting = false
                    }
                },
                enabled = !isSubmitting && locationResult != null,
                colors = ButtonDefaults.buttonColors(containerColor = BrandNavy),
                shape = RoundedCornerShape(10.dp)
            ) {
                if (isSubmitting) {
                    CircularProgressIndicator(modifier = Modifier.size(16.dp), color = BrandWhite, strokeWidth = 2.dp)
                } else {
                    Text("Submit for Approval", color = BrandWhite, fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                }
            }
        },
        dismissButton = {
            OutlinedButton(
                onClick = onDismiss,
                shape = RoundedCornerShape(10.dp),
                border = BorderStroke(1.dp, BrandLightGray),
                enabled = !isSubmitting
            ) {
                Text("Cancel", color = TextSecondary, fontFamily = LeagueSpartanFamily, fontSize = 13.sp)
            }
        }
    )
}
