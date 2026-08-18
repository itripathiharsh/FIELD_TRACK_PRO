package com.fieldtrackpro.android.ui.components

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.MyLocation
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
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
import com.fieldtrackpro.android.services.LocationCaptureService
import com.fieldtrackpro.android.services.LocationResult
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandLightGray
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.ErrorRed
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.theme.LibreBaskervilleFamily
import com.fieldtrackpro.android.ui.theme.SuccessGreen
import com.fieldtrackpro.android.ui.theme.TextSecondary
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

    fun capture() {
        isCapturing = true
        statusText = null
        isError = false
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
        }
    }

    Column(modifier = modifier.fillMaxWidth()) {
        Button(
            onClick = {
                if (locationService.hasLocationPermission()) {
                    capture()
                } else {
                    permissionLauncher.launch(
                        arrayOf(
                            Manifest.permission.ACCESS_FINE_LOCATION,
                            Manifest.permission.ACCESS_COARSE_LOCATION
                        )
                    )
                }
            },
            enabled = !isCapturing,
            shape = RoundedCornerShape(10.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = BrandNavy,
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
