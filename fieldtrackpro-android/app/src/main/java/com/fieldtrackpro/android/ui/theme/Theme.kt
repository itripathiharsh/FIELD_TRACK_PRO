package com.fieldtrackpro.android.ui.theme

import android.app.Activity
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Shapes
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.unit.dp
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

val FieldTrackShapes = Shapes(
    extraSmall = RoundedCornerShape(8.dp),
    small = RoundedCornerShape(10.dp),
    medium = RoundedCornerShape(12.dp),
    large = RoundedCornerShape(20.dp),
    extraLarge = RoundedCornerShape(28.dp)
)

/**
 * The window is edge-to-edge (MainActivity.enableEdgeToEdge, and enforced by Android 15 for targetSdk 35), so the
 * status bar is transparent and only its icon colour can be chosen. Light screens need DARK icons; the old code forced
 * light icons everywhere, which made them invisible on the white top bars.
 */
@Composable
fun SystemBarIcons(darkIcons: Boolean) {
    val view = LocalView.current
    if (view.isInEditMode) return
    DisposableEffect(darkIcons) {
        val window = (view.context as? Activity)?.window
        val controller = window?.let { WindowCompat.getInsetsController(it, view) }
        val previous = controller?.isAppearanceLightStatusBars
        controller?.isAppearanceLightStatusBars = darkIcons
        controller?.isAppearanceLightNavigationBars = darkIcons
        onDispose {
            if (previous != null) {
                controller.isAppearanceLightStatusBars = previous
                controller.isAppearanceLightNavigationBars = previous
            }
        }
    }
}

@Composable
fun FieldTrackProTheme(
    content: @Composable () -> Unit
) {
    MaterialTheme(
        colorScheme = FieldTrackColorScheme,
        typography = Typography,
        shapes = FieldTrackShapes,
        content = content
    )
}
