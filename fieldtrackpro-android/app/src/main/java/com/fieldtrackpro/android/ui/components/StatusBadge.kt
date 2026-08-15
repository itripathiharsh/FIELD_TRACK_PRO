package com.fieldtrackpro.android.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.ui.theme.ErrorRed
import com.fieldtrackpro.android.ui.theme.FieldTrackAmber
import com.fieldtrackpro.android.ui.theme.FieldTrackNavy
import com.fieldtrackpro.android.ui.theme.SuccessGreen
import com.fieldtrackpro.android.ui.theme.TextMuted

@Composable
fun StatusBadge(status: String, modifier: Modifier = Modifier) {
    val (bgColor, textColor, label) = when (status.uppercase()) {
        "PENDING" -> Triple(FieldTrackNavy.copy(alpha = 0.15f), FieldTrackNavy, "PENDING")
        "IN_PROGRESS" -> Triple(SuccessGreen.copy(alpha = 0.15f), SuccessGreen, "IN PROGRESS")
        "COMPLETED", "VERIFIED", "PAID", "NORMAL" -> Triple(SuccessGreen.copy(alpha = 0.2f), SuccessGreen, status.uppercase().replace('_', ' '))
        "FLAGGED", "WARNING", "PARTIALLY_PAID" -> Triple(FieldTrackAmber.copy(alpha = 0.2f), FieldTrackAmber, status.uppercase().replace('_', ' '))
        "MISSED", "OVERDUE", "REJECTED" -> Triple(ErrorRed.copy(alpha = 0.15f), ErrorRed, status.uppercase().replace('_', ' '))
        "PENDING_VERIFICATION", "UNPAID" -> Triple(FieldTrackNavy.copy(alpha = 0.15f), FieldTrackNavy, status.uppercase().replace('_', ' '))
        else -> Triple(TextMuted.copy(alpha = 0.15f), TextMuted, status.uppercase())
    }

    Box(
        modifier = modifier
            .clip(RoundedCornerShape(6.dp))
            .background(bgColor)
            .padding(horizontal = 10.dp, vertical = 4.dp)
    ) {
        Text(
            text = label,
            fontSize = 11.sp,
            fontWeight = FontWeight.Bold,
            color = textColor
        )
    }
}
