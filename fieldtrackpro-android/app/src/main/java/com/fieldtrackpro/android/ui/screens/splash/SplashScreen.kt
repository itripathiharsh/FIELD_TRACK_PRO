package com.fieldtrackpro.android.ui.screens.splash

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.ui.components.BrandMark
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.theme.Navy950
import com.fieldtrackpro.android.ui.theme.SystemBarIcons
import com.fieldtrackpro.android.utils.StartDestination
import com.fieldtrackpro.android.utils.StartRouting
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Splash Screen.
 *
 * APP-AUTH-002: routes from STORED state only (see [StartRouting]) - no network call, no eager token refresh.
 * A stored session opens the dashboard immediately (also offline); expiry is handled lazily by
 * TokenAuthenticator on the first authenticated request.
 *
 * Design v2: this frame continues the system launch window (navy + the mark at the same size and position, see
 * res/values-v31/themes.xml), so there is one splash, not two. There is no fixed delay any more: the wordmark fades in
 * while the stored session is read off the main thread, and navigation happens as soon as routing is decided.
 */
@Composable
fun SplashScreen(
    tokenManager: TokenManager,
    onNavigateToLogin: () -> Unit,
    onNavigateToDashboard: () -> Unit,
    onNavigateToChangePassword: () -> Unit = onNavigateToLogin
) {
    LaunchedEffect(Unit) {
        // Opening the Keystore-backed prefs can take a moment on first launch: keep it off the main thread.
        val destination = withContext(Dispatchers.IO) { StartRouting.decide(tokenManager) }
        when (destination) {
            StartDestination.DASHBOARD -> onNavigateToDashboard()
            StartDestination.CHANGE_PASSWORD -> onNavigateToChangePassword()
            StartDestination.LOGIN -> onNavigateToLogin()
        }
    }
    SplashContent()
}

/** Stateless splash visuals (also used by the screenshot test). */
@Composable
fun SplashContent(animate: Boolean = true) {
    SystemBarIcons(darkIcons = false)
    val reveal = remember { Animatable(if (animate) 0f else 1f) }
    LaunchedEffect(animate) {
        if (animate) reveal.animateTo(1f, tween(durationMillis = 420, easing = FastOutSlowInEasing))
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.radialGradient(
                    colors = listOf(Color(0xFF1F3263), BrandNavy, Navy950),
                    radius = 1400f
                )
            ),
        contentAlignment = Alignment.Center
    ) {
        // Same size and centre as the system splash icon (ic_splash_mark: ~96 dp tall mark).
        BrandMark(height = 102.dp, contentDescription = "FieldTrack Pro")

        Column(
            modifier = Modifier
                .offset(y = 104.dp)
                .alpha(reveal.value)
                .offset(y = ((1f - reveal.value) * 12f).dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                text = "FieldTrack Pro",
                fontFamily = LeagueSpartanFamily,
                fontWeight = FontWeight.Bold,
                fontSize = 30.sp,
                letterSpacing = (-0.4).sp,
                color = BrandWhite
            )
            Spacer(Modifier.height(8.dp))
            Text(
                text = "FIELD FORCE · VERIFIED",
                fontFamily = LeagueSpartanFamily,
                fontWeight = FontWeight.SemiBold,
                fontSize = 12.sp,
                letterSpacing = 2.4.sp,
                color = BrandGold
            )
        }

        Text(
            text = "SGRG Distribution",
            fontFamily = LeagueSpartanFamily,
            fontWeight = FontWeight.Medium,
            fontSize = 12.sp,
            letterSpacing = 0.6.sp,
            color = BrandWhite.copy(alpha = 0.55f),
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .navigationBarsPadding()
                .padding(bottom = 28.dp)
                .alpha(reveal.value)
        )
    }
}
