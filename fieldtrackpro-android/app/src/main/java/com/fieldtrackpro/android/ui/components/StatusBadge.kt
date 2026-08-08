package com.fieldtrackpro.android.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.ui.theme.AmberWarning
import com.fieldtrackpro.android.ui.theme.CoralRed
import com.fieldtrackpro.android.ui.theme.ElectricBlue
import com.fieldtrackpro.android.ui.theme.EmeraldGreen
import com.fieldtrackpro.android.ui.theme.Slate500

@Composable
fun StatusBadge(status: String, modifier: Modifier = Modifier) {
    val (bgColor, textColor, label) = when (status.uppercase()) {
        "PENDING" -> Triple(ElectricBlue.copy(alpha = 0.15f), ElectricBlue, "PENDING")
        "IN_PROGRESS" -> Triple(EmeraldGreen.copy(alpha = 0.15f), EmeraldGreen, "IN PROGRESS")
        "COMPLETED" -> Triple(EmeraldGreen.copy(alpha = 0.2f), EmeraldGreen, "COMPLETED")
        "FLAGGED" -> Triple(AmberWarning.copy(alpha = 0.2f), AmberWarning, "FLAGGED")
        "MISSED" -> Triple(CoralRed.copy(alpha = 0.15f), CoralRed, "MISSED")
        else -> Triple(Slate500.copy(alpha = 0.15f), Slate500, status.uppercase())
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
