package com.fieldtrackpro.android.ui.components

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.material.icons.filled.LocationOff
import androidx.compose.material.icons.filled.MyLocation
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.fieldtrackpro.android.services.LocationCaptureService
import com.fieldtrackpro.android.services.LocationPermissionDeniedException
import com.fieldtrackpro.android.services.LocationResult
import com.fieldtrackpro.android.services.LocationServicesDisabledException
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandLightGray
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.ErrorRed
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.theme.LibreBaskervilleFamily
import com.fieldtrackpro.android.ui.theme.SuccessGreen
import com.fieldtrackpro.android.ui.theme.TextSecondary
import com.fieldtrackpro.android.utils.LocationSettingsHelper
import kotlinx.coroutines.launch

@Composable
fun LocationCaptureButton(
    onCaptured: (LocationResult) -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val locationService = remember { LocationCaptureService(context) }
    val coroutineScope = rememberCoroutineScope()

    var isCapturing by remember { mutableStateOf(false) }
    var statusText by remember { mutableStateOf<String?>(null) }
    var isError by remember { mutableStateOf(false) }
    var isLocationDisabled by remember { mutableStateOf(false) }
    var isPermissionDenied by remember { mutableStateOf(false) }

    fun capture() {
        isCapturing = true
        statusText = null
        isError = false
        isLocationDisabled = false
        isPermissionDenied = false

        coroutineScope.launch {
            try {
                val result = locationService.getCurrentLocation()
                if (!result.isAccuracyAcceptable) {
                    statusText = "GPS accuracy too poor (±${result.accuracy.toInt()}m). Move to open sky and retry."
                    isError = true
                } else {
                    onCaptured(result)
                    statusText = "GPS Fix Acquired (±${result.accuracy.toInt()}m accuracy) ✓"
                    isError = false
                }
            } catch (e: LocationServicesDisabledException) {
                statusText = "Location is turned off. Please enable Location to check in."
                isError = true
                isLocationDisabled = true
            } catch (e: LocationPermissionDeniedException) {
                statusText = "Location permission not granted. Please allow precise location access."
                isError = true
                isPermissionDenied = true
            } catch (e: Exception) {
                statusText = e.message ?: "Could not capture GPS location"
                isError = true
            } finally {
                isCapturing = false
            }
        }
    }

    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestMultiplePermissions()
    ) { grants ->
        val granted = grants[Manifest.permission.ACCESS_FINE_LOCATION] == true ||
            grants[Manifest.permission.ACCESS_COARSE_LOCATION] == true
        if (granted) {
            capture()
        } else {
            statusText = "Location permission denied. Enable it to capture GPS coordinates."
            isError = true
            isPermissionDenied = true
        }
    }

    // Lifecycle observer to auto re-check on resume when returning from settings
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                if (isLocationDisabled && locationService.isLocationEnabled()) {
                    isLocationDisabled = false
                    statusText = null
                    isError = false
                    capture()
                }
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
        }
    }

    Column(modifier = modifier.fillMaxWidth()) {
        Button(
            onClick = {
                if (isLocationDisabled || !locationService.isLocationEnabled()) {
                    LocationSettingsHelper.openLocationSettings(context)
                } else if (!locationService.hasLocationPermission()) {
                    permissionLauncher.launch(
                        arrayOf(
                            Manifest.permission.ACCESS_FINE_LOCATION,
                            Manifest.permission.ACCESS_COARSE_LOCATION
                        )
                    )
                } else {
                    capture()
                }
            },
            enabled = !isCapturing,
            shape = RoundedCornerShape(10.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = if (isLocationDisabled) BrandNavy else BrandNavy,
                contentColor = BrandWhite
            ),
            modifier = Modifier
                .fillMaxWidth()
                .height(48.dp)
        ) {
            if (isCapturing) {
                CircularProgressIndicator(
                    color = BrandGold,
                    modifier = Modifier.size(20.dp),
                    strokeWidth = 2.dp
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    "ACQUIRING PRECISION GPS...",
                    fontFamily = LeagueSpartanFamily,
                    fontWeight = FontWeight.Bold,
                    fontSize = 13.sp,
                    color = BrandWhite
                )
            } else if (isLocationDisabled) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = Icons.Default.LocationOff,
                        contentDescription = null,
                        tint = BrandGold,
                        modifier = Modifier.size(18.dp)
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        "ENABLE LOCATION (OPEN SETTINGS)",
                        fontFamily = LeagueSpartanFamily,
                        fontWeight = FontWeight.Bold,
                        fontSize = 13.sp,
                        letterSpacing = 0.5.sp,
                        color = BrandWhite
                    )
                }
            } else {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = Icons.Default.MyLocation,
                        contentDescription = null,
                        tint = BrandGold,
                        modifier = Modifier.size(18.dp)
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        "CAPTURE CURRENT GPS LOCATION",
                        fontFamily = LeagueSpartanFamily,
                        fontWeight = FontWeight.Bold,
                        fontSize = 13.sp,
                        letterSpacing = 0.5.sp,
                        color = BrandWhite
                    )
                }
            }
        }

        if (isLocationDisabled) {
            Spacer(modifier = Modifier.height(8.dp))
            OutlinedButton(
                onClick = { LocationSettingsHelper.openLocationSettings(context) },
                modifier = Modifier.fillMaxWidth().height(42.dp),
                shape = RoundedCornerShape(8.dp)
            ) {
                Icon(
                    imageVector = Icons.Default.Settings,
                    contentDescription = null,
                    tint = BrandNavy,
                    modifier = Modifier.size(16.dp)
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    "OPEN ANDROID LOCATION SETTINGS",
                    fontFamily = LeagueSpartanFamily,
                    fontWeight = FontWeight.Bold,
                    fontSize = 12.sp,
                    color = BrandNavy
                )
            }
        }

        statusText?.let {
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = it,
                fontFamily = LibreBaskervilleFamily,
                fontSize = 12.sp,
                color = if (isError) ErrorRed else SuccessGreen,
                fontWeight = if (isError) FontWeight.Normal else FontWeight.Bold
            )
        }
    }
}
