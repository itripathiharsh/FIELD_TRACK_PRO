package com.fieldtrackpro.android.ui.components

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
    modifier: Modifier = Modifier,
) {
    val status = getGeofenceStatus(isInside, isOutside, hasPermission, isLocationEnabled, isMonitoring, errorMessage)

    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
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
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Bold,
                    color = TextPrimary
                )
                Text(
                    text = status.subtitle,
                    fontSize = 12.sp,
                    color = TextMuted
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
): GeofenceStatus {
    return when {
        errorMessage != null -> GeofenceStatus(
            icon = Icons.Default.Error,
            iconColor = ErrorRed,
            title = "Geofence monitoring error",
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
            subtitle = "Enable location services to continue."
        )
        isInside -> GeofenceStatus(
            icon = Icons.Default.CheckCircle,
            iconColor = SuccessGreen,
            title = "You're within the visit area",
            subtitle = "Ready to check in."
        )
        isOutside -> GeofenceStatus(
            icon = Icons.Default.Error,
            iconColor = ErrorRed,
            title = "You're outside the visit area",
            subtitle = "Move closer to the customer location to check in."
        )
        isMonitoring -> GeofenceStatus(
            icon = Icons.Default.LocationOn,
            iconColor = TextMuted,
            title = "Determining location...",
            subtitle = "Please wait while we verify your location."
        )
        else -> GeofenceStatus(
            icon = Icons.Default.Warning,
            iconColor = TextMuted,
            title = "Location status unknown",
            subtitle = "Please try again."
        )
    }
}
