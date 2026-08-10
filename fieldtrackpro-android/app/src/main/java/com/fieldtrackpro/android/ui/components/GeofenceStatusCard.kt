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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.ui.theme.EmeraldGreen
import com.fieldtrackpro.android.ui.theme.CoralRed
import androidx.compose.ui.graphics.vector.ImageVector
import com.fieldtrackpro.android.ui.theme.AmberWarning
import com.fieldtrackpro.android.ui.theme.Slate50
import com.fieldtrackpro.android.ui.theme.Slate500
import com.fieldtrackpro.android.ui.theme.Slate900
import com.fieldtrackpro.android.ui.theme.SurfaceWhite

/**
 * Displays the current geofence status for a visit.
 *
 * Shows:
 * - Inside geofence (green)
 * - Outside geofence (red)
 * - Permission missing (amber)
 * - Location disabled (amber)
 * - Unknown/loading state
 */
@Composable
fun GeofenceStatusCard(
    isInside: Boolean,
    isOutside: Boolean,
    hasPermission: Boolean,
    isLocationEnabled: Boolean,
    isMonitoring: Boolean,
    modifier: Modifier = Modifier,
) {
    val status = getGeofenceStatus(isInside, isOutside, hasPermission, isLocationEnabled, isMonitoring)

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
                    color = Slate900
                )
                Text(
                    text = status.subtitle,
                    fontSize = 12.sp,
                    color = Slate500
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
): GeofenceStatus {
    return when {
        !hasPermission -> GeofenceStatus(
            icon = Icons.Default.Warning,
            iconColor = AmberWarning,
            title = "Location permission required",
            subtitle = "Allow location access to verify that you're at the customer site."
        )
        !isLocationEnabled -> GeofenceStatus(
            icon = Icons.Default.LocationOff,
            iconColor = AmberWarning,
            title = "Location services disabled",
            subtitle = "Enable location services to continue."
        )
        isInside -> GeofenceStatus(
            icon = Icons.Default.CheckCircle,
            iconColor = EmeraldGreen,
            title = "You're within the visit area",
            subtitle = "Ready to check in."
        )
        isOutside -> GeofenceStatus(
            icon = Icons.Default.Error,
            iconColor = CoralRed,
            title = "You're outside the visit area",
            subtitle = "Move closer to the customer location to check in."
        )
        isMonitoring -> GeofenceStatus(
            icon = Icons.Default.LocationOn,
            iconColor = Slate500,
            title = "Determining location...",
            subtitle = "Please wait while we verify your location."
        )
        else -> GeofenceStatus(
            icon = Icons.Default.Warning,
            iconColor = Slate500,
            title = "Location status unknown",
            subtitle = "Please try again."
        )
    }
}
