package com.fieldtrackpro.android.ui.components

import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Error
import androidx.compose.material.icons.filled.LocationOff
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.Warning
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
import com.fieldtrackpro.android.ui.theme.ErrorRed
import com.fieldtrackpro.android.ui.theme.FieldTrackAmber
import com.fieldtrackpro.android.ui.theme.FieldTrackNavy
import com.fieldtrackpro.android.ui.theme.SuccessGreen
import com.fieldtrackpro.android.ui.theme.SurfaceWhite
import com.fieldtrackpro.android.ui.theme.TextMuted
import com.fieldtrackpro.android.ui.theme.TextPrimary

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
            .border(1.dp, com.fieldtrackpro.android.ui.theme.BrandLightGray, RoundedCornerShape(12.dp)),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = com.fieldtrackpro.android.ui.theme.BrandWhite),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
    ) {
        Row(
            modifier = Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = status.icon,
                contentDescription = null,
                tint = status.iconColor,
                modifier = Modifier.size(32.dp)
            )
            Spacer(modifier = Modifier.size(12.dp))
            Column {
                Text(
                    text = status.title,
                    fontFamily = com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily,
                    fontSize = 15.sp,
                    fontWeight = FontWeight.Bold,
                    color = com.fieldtrackpro.android.ui.theme.BrandNavy
                )
                Spacer(modifier = Modifier.size(2.dp))
                Text(
                    text = status.subtitle,
                    fontFamily = com.fieldtrackpro.android.ui.theme.LibreBaskervilleFamily,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Normal,
                    color = com.fieldtrackpro.android.ui.theme.TextSecondary
                )
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
            title = "Location services disabled",
            subtitle = "Turn on GPS in device settings to continue."
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
