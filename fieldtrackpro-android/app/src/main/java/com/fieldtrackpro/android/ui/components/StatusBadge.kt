package com.fieldtrackpro.android.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.ui.theme.BrandBlack
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandLightGray
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.ErrorRed
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.theme.SuccessGreen
import com.fieldtrackpro.android.ui.theme.TextSecondary

@Composable
fun StatusBadge(status: String, modifier: Modifier = Modifier) {
    val (bgColor, borderColor, textColor, label) = when (status.uppercase()) {
        "PENDING", "SCHEDULED" -> Quadruple(
            Color(0xFFF0F2F5),
            BrandLightGray,
            BrandNavy,
            status.uppercase().replace('_', ' ')
        )
        "IN_PROGRESS" -> Quadruple(
            Color(0xFFFFF4DE),
            BrandGold.copy(alpha = 0.5f),
            Color(0xFFB45309),
            "IN PROGRESS"
        )
        "COMPLETED", "VERIFIED", "PAID", "NORMAL" -> Quadruple(
            Color(0xFFD1FAE5),
            SuccessGreen.copy(alpha = 0.4f),
            Color(0xFF065F46),
            status.uppercase().replace('_', ' ')
        )
        "FLAGGED", "WARNING", "PARTIALLY_PAID" -> Quadruple(
            Color(0xFFFEF3C7),
            BrandGold,
            Color(0xFF92400E),
            status.uppercase().replace('_', ' ')
        )
        "MISSED", "OVERDUE", "REJECTED" -> Quadruple(
            Color(0xFFFEE2E2),
            ErrorRed.copy(alpha = 0.4f),
            Color(0xFF991B1B),
            status.uppercase().replace('_', ' ')
        )
        "PENDING_VERIFICATION", "UNPAID" -> Quadruple(
            Color(0xFFF0F2F5),
            BrandLightGray,
            BrandNavy,
            status.uppercase().replace('_', ' ')
        )
        else -> Quadruple(
            Color(0xFFF0F2F5),
            BrandLightGray,
            TextSecondary,
            status.uppercase()
        )
    }

    Box(
        modifier = modifier
            .clip(RoundedCornerShape(6.dp))
            .background(bgColor)
            .border(1.dp, borderColor, RoundedCornerShape(6.dp))
            .padding(horizontal = 8.dp, vertical = 3.dp)
    ) {
        Text(
            text = label,
            fontFamily = LeagueSpartanFamily,
            fontSize = 11.sp,
            fontWeight = FontWeight.Bold,
            letterSpacing = 0.5.sp,
            color = textColor
        )
    }
}

private data class Quadruple<A, B, C, D>(val first: A, val second: B, val third: C, val fourth: D)
