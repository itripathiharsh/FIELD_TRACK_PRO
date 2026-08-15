package com.fieldtrackpro.android.ui.components

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.services.LocationCaptureService
import com.fieldtrackpro.android.services.LocationResult
import com.fieldtrackpro.android.ui.theme.ErrorRed
import com.fieldtrackpro.android.ui.theme.FieldTrackNavy
import com.fieldtrackpro.android.ui.theme.TextMuted
import kotlinx.coroutines.launch

/**
 * Captures the device's real GPS position for check-in/check-out.
 *
 * Requests ACCESS_FINE_LOCATION/ACCESS_COARSE_LOCATION at the point of use if
 * not already granted (the app previously never requested location
 * permission anywhere, so geofencing/GPS capture could never start on a
 * fresh install), then reads a fix via [LocationCaptureService].
 */
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

    fun capture() {
        isCapturing = true
        statusText = null
        isError = false
        coroutineScope.launch {
            try {
                val result = locationService.getCurrentLocation()
                if (!result.isAccuracyAcceptable) {
                    // P1-9: a fix this poor would be rejected by the server's
                    // own accuracy check anyway (GeoVerificationService) - do
                    // not hand it to onCaptured (which would otherwise let
                    // check-in/out's "real capture obtained" gate treat this
                    // as good enough to submit). The existing "tap the
                    // button again to retry" flow already covers this.
                    statusText = "GPS accuracy too poor (±${result.accuracy.toInt()}m). " +
                        "Move to open sky and try again."
                    isError = true
                } else {
                    onCaptured(result)
                    statusText = "Captured (±${result.accuracy.toInt()}m accuracy)"
                    isError = false
                }
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
            statusText = "Location permission denied. Enable it to auto-capture GPS."
            isError = true
        }
    }

    Column(modifier = modifier.fillMaxWidth()) {
        OutlinedButton(
            onClick = {
                if (locationService.hasLocationPermission()) {
                    capture()
                } else {
                    permissionLauncher.launch(
                        arrayOf(
                            Manifest.permission.ACCESS_FINE_LOCATION,
                            Manifest.permission.ACCESS_COARSE_LOCATION,
                        )
                    )
                }
            },
            enabled = !isCapturing,
            modifier = Modifier.fillMaxWidth()
        ) {
            if (isCapturing) {
                CircularProgressIndicator(modifier = Modifier.size(18.dp), color = FieldTrackNavy)
            } else {
                Text("USE MY CURRENT LOCATION", color = FieldTrackNavy)
            }
        }
        statusText?.let {
            Text(
                text = it,
                fontSize = 12.sp,
                color = if (isError) ErrorRed else TextMuted,
            )
        }
    }
}
