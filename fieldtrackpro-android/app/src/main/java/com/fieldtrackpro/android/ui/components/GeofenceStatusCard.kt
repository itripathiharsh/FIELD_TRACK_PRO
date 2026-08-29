package com.fieldtrackpro.android.ui.components

import androidx.compose.foundation.border
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
import androidx.compose.material.icons.filled.Error
import androidx.compose.material.icons.filled.LocationOff
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandLightGray
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.ErrorRed
import com.fieldtrackpro.android.ui.theme.FieldTrackAmber
import com.fieldtrackpro.android.ui.theme.FieldTrackNavy
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.theme.LibreBaskervilleFamily
import com.fieldtrackpro.android.ui.theme.SuccessGreen
import com.fieldtrackpro.android.ui.theme.TextMuted
import com.fieldtrackpro.android.ui.theme.TextSecondary

@Composable
fun GeofenceStatusCard(
    isInside: Boolean,
    isOutside: Boolean,
    hasPermission: Boolean,
    isLocationEnabled: Boolean,
    isMonitoring: Boolean,
    errorMessage: String? = null,
    distanceM: Double? = null,
    geofenceRadiusM: Double? = null,
    isLoadingLocation: Boolean = false,
    onEnableLocationClick: (() -> Unit)? = null,
    onRequestPermissionClick: (() -> Unit)? = null,
    modifier: Modifier = Modifier,
) {
    val status = getGeofenceStatus(
        isInside = isInside,
        isOutside = isOutside,
        hasPermission = hasPermission,
        isLocationEnabled = isLocationEnabled,
        isMonitoring = isMonitoring,
        errorMessage = errorMessage,
        distanceM = distanceM,
        geofenceRadiusM = geofenceRadiusM,
        isLoadingLocation = isLoadingLocation
    )

    Card(
        modifier = modifier
            .fillMaxWidth()
            .border(1.dp, BrandLightGray, RoundedCornerShape(12.dp)),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = BrandWhite),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = status.icon,
                    contentDescription = null,
                    tint = status.iconColor,
                    modifier = Modifier.size(32.dp)
                )
                Spacer(modifier = Modifier.size(12.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = status.title,
                        fontFamily = LeagueSpartanFamily,
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Bold,
                        color = BrandNavy
                    )
                    Spacer(modifier = Modifier.size(2.dp))
                    Text(
                        text = status.subtitle,
                        fontFamily = LibreBaskervilleFamily,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Normal,
                        color = TextSecondary
                    )
                }
            }

            if (!isLocationEnabled && onEnableLocationClick != null) {
                Spacer(modifier = Modifier.height(12.dp))
                Button(
                    onClick = onEnableLocationClick,
                    modifier = Modifier.fillMaxWidth().height(42.dp),
                    shape = RoundedCornerShape(8.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = BrandNavy,
                        contentColor = BrandWhite
                    )
                ) {
                    Icon(
                        imageVector = Icons.Default.Settings,
                        contentDescription = null,
                        tint = BrandGold,
                        modifier = Modifier.size(18.dp)
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = "ENABLE LOCATION",
                        fontFamily = LeagueSpartanFamily,
                        fontWeight = FontWeight.Bold,
                        fontSize = 13.sp,
                        letterSpacing = 0.5.sp,
                        color = BrandWhite
                    )
                }
            } else if (!hasPermission && onRequestPermissionClick != null) {
                Spacer(modifier = Modifier.height(12.dp))
                Button(
                    onClick = onRequestPermissionClick,
                    modifier = Modifier.fillMaxWidth().height(42.dp),
                    shape = RoundedCornerShape(8.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = BrandNavy,
                        contentColor = BrandWhite
                    )
                ) {
                    Icon(
                        imageVector = Icons.Default.LocationOn,
                        contentDescription = null,
                        tint = BrandGold,
                        modifier = Modifier.size(18.dp)
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = "GRANT LOCATION PERMISSION",
                        fontFamily = LeagueSpartanFamily,
                        fontWeight = FontWeight.Bold,
                        fontSize = 13.sp,
                        letterSpacing = 0.5.sp,
                        color = BrandWhite
                    )
                }
            }
        }
    }
}

private data class GeofenceStatus(
    val icon: ImageVector,
    val iconColor: Color,
    val title: String,
    val subtitle: String,
)

private fun getGeofenceStatus(
    isInside: Boolean,
    isOutside: Boolean,
    hasPermission: Boolean,
    isLocationEnabled: Boolean,
    isMonitoring: Boolean,
    errorMessage: String? = null,
    distanceM: Double? = null,
    geofenceRadiusM: Double? = null,
    isLoadingLocation: Boolean = false,
): GeofenceStatus {
    return when {
        errorMessage != null -> GeofenceStatus(
            icon = Icons.Default.Error,
            iconColor = ErrorRed,
            title = "Location Notice",
            subtitle = errorMessage
        )
        !hasPermission -> GeofenceStatus(
            icon = Icons.Default.Warning,
            iconColor = FieldTrackAmber,
            title = "Location permission required",
            subtitle = "Allow location access to verify that you're at the customer site."
        )
        !isLocationEnabled -> GeofenceStatus(
            icon = Icons.Default.LocationOff,
            iconColor = FieldTrackAmber,
            title = "Location is turned off",
            subtitle = "Location is turned off. Please enable Location to check in."
        )
        isLoadingLocation -> GeofenceStatus(
            icon = Icons.Default.LocationOn,
            iconColor = FieldTrackNavy,
            title = "Determining location...",
            subtitle = "Measuring distance to customer outlet..."
        )
        isInside -> {
            val distText = if (distanceM != null) "${distanceM.toInt()}m from outlet. Ready to check in." else "Ready to check in."
            GeofenceStatus(
                icon = Icons.Default.CheckCircle,
                iconColor = SuccessGreen,
                title = "Inside Outlet Radius",
                subtitle = distText
            )
        }
        isOutside -> {
            val distText = if (distanceM != null && geofenceRadiusM != null) {
                "${distanceM.toInt()}m away (allowed radius: ${geofenceRadiusM.toInt()}m). Move closer to check in."
            } else if (distanceM != null) {
                "${distanceM.toInt()}m away. Move closer to the customer location to check in."
            } else {
                "Move closer to the customer location to check in."
            }
            GeofenceStatus(
                icon = Icons.Default.Error,
                iconColor = ErrorRed,
                title = "Outside Outlet Radius",
                subtitle = distText
            )
        }
        isMonitoring -> GeofenceStatus(
            icon = Icons.Default.LocationOn,
            iconColor = TextMuted,
            title = "Monitoring location proximity",
            subtitle = "Move to the customer site to check in."
        )
        else -> GeofenceStatus(
            icon = Icons.Default.LocationOn,
            iconColor = TextMuted,
            title = "Getting location status...",
            subtitle = "Please wait while we determine your position."
        )
    }
}
