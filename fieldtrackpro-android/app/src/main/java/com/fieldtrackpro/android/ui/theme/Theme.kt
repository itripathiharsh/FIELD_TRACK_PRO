package com.fieldtrackpro.android.ui.theme

import android.app.Activity
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

/**
 * FieldTrack Pro Centralized Material 3 Color Scheme
 *
 * Mapped directly to official Brand Design System:
 * - primary:            #14213D (BrandNavy)
 * - onPrimary:          #FFFFFF (BrandWhite)
 * - primaryContainer:   #0A1120 (BrandNavyDark)
 * - onPrimaryContainer: #FFFFFF (BrandWhite)
 * - secondary:          #FCA311 (BrandGold)
 * - onSecondary:        #000000 (BrandBlack)
 * - secondaryContainer: #FFF4DE (BrandGoldLight)
 * - onSecondaryContainer: #78350F (BrandGoldDark/Contrast)
 * - background:         #F8F9FA (SurfaceSecondary)
 * - onBackground:       #14213D (BrandNavy)
 * - surface:            #FFFFFF (BrandWhite)
 * - onSurface:          #14213D (BrandNavy)
 * - surfaceVariant:     #F0F1F3
 * - onSurfaceVariant:   #45464D (TextSecondary)
 * - outline:            #E5E5E5 (BrandLightGray)
 * - error:              #EF4444 (ErrorRed)
 * - onError:            #FFFFFF (BrandWhite)
 */

val FieldTrackColorScheme = lightColorScheme(
    primary = BrandNavy,
    onPrimary = BrandWhite,
    primaryContainer = BrandNavyLight,
    onPrimaryContainer = BrandWhite,
    secondary = BrandGold,
    onSecondary = BrandBlack,
    secondaryContainer = BrandGoldLight,
    onSecondaryContainer = BrandGoldDark,
    tertiary = BrandGold,
    onTertiary = BrandBlack,
    background = SurfaceSecondary,
    onBackground = TextPrimary,
    surface = SurfacePrimary,
    onSurface = TextPrimary,
    surfaceVariant = SurfaceContainer,
    onSurfaceVariant = TextSecondary,
    outline = BorderSubtle,
    outlineVariant = BorderSubtle,
    error = ErrorRed,
    onError = BrandWhite,
    errorContainer = ErrorRedBg,
    onErrorContainer = ErrorRedText
)

@Composable
fun FieldTrackProTheme(
    content: @Composable () -> Unit
) {
    val colorScheme = FieldTrackColorScheme
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            window.statusBarColor = colorScheme.primary.toArgb()
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = false
        }
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = Typography,
        content = content
    )
}
