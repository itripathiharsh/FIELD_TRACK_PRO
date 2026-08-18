package com.fieldtrackpro.android.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily

@Composable
fun OfflineSyncBanner(pendingCount: Int, onSyncClick: () -> Unit, modifier: Modifier = Modifier) {
    if (pendingCount <= 0) return

    Row(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(BrandGold.copy(alpha = 0.15f))
            .border(1.dp, BrandGold, RoundedCornerShape(10.dp))
            .clickable { onSyncClick() }
            .padding(14.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(
            imageVector = Icons.Default.Sync,
            contentDescription = "Sync",
            tint = BrandNavy,
            modifier = Modifier.size(20.dp)
        )
        Spacer(modifier = Modifier.width(10.dp))
        Text(
            text = "$pendingCount offline action(s) stored locally. Tap to sync.",
            fontFamily = LeagueSpartanFamily,
            fontSize = 13.sp,
            fontWeight = FontWeight.Bold,
            color = BrandNavy,
            modifier = Modifier.weight(1f)
        )
    }
}
