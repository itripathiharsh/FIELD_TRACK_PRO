package com.fieldtrackpro.android.ui.screens.splash

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Shield
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.utils.StartDestination
import com.fieldtrackpro.android.utils.StartRouting
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.theme.LibreBaskervilleFamily
import kotlinx.coroutines.delay

/**
 * Splash Screen.
 *
 * APP-AUTH-002: routes from STORED state only (see [StartRouting]) - no network call, no eager token refresh.
 * A stored session opens the dashboard immediately (also offline); expiry is handled lazily by
 * TokenAuthenticator on the first authenticated request.
 */
@Composable
fun SplashScreen(
    tokenManager: TokenManager,
    onNavigateToLogin: () -> Unit,
    onNavigateToDashboard: () -> Unit,
    onNavigateToChangePassword: () -> Unit = onNavigateToLogin
) {
    LaunchedEffect(Unit) {
        val destination = StartRouting.decide(tokenManager)
        delay(400)
        when (destination) {
            StartDestination.DASHBOARD -> onNavigateToDashboard()
            StartDestination.CHANGE_PASSWORD -> onNavigateToChangePassword()
            StartDestination.LOGIN -> onNavigateToLogin()
        }
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(BrandNavy),
        contentAlignment = Alignment.Center
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Box(
                modifier = Modifier
                    .size(72.dp)
                    .clip(RoundedCornerShape(16.dp))
                    .background(BrandNavy)
                    .border(2.dp, BrandGold, RoundedCornerShape(16.dp)),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    imageVector = Icons.Default.Shield,
                    contentDescription = null,
                    tint = BrandGold,
                    modifier = Modifier.size(42.dp)
                )
            }

            Spacer(modifier = Modifier.height(18.dp))

            Text(
                text = "FieldTrack Pro",
                fontFamily = LeagueSpartanFamily,
                fontWeight = FontWeight.Bold,
                fontSize = 32.sp,
                letterSpacing = (-0.5).sp,
                color = BrandWhite
            )

            Spacer(modifier = Modifier.height(6.dp))

            Text(
                text = "Precision Geolocation & Field Force Intelligence",
                fontFamily = LibreBaskervilleFamily,
                fontSize = 13.sp,
                color = BrandGold
            )

            Spacer(modifier = Modifier.height(36.dp))

            CircularProgressIndicator(
                color = BrandGold,
                modifier = Modifier.size(32.dp),
                strokeWidth = 3.dp
            )
        }
    }
}
