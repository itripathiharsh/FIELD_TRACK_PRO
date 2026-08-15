package com.fieldtrackpro.android.ui.theme

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

private val LightColorScheme = lightColorScheme(
    primary = FieldTrackNavy,
    onPrimary = SurfaceWhite,
    primaryContainer = FieldTrackNavyLight,
    onPrimaryContainer = SurfaceWhite,
    secondary = FieldTrackAmber,
    onSecondary = FieldTrackNavy,
    secondaryContainer = FieldTrackAmberLight,
    onSecondaryContainer = FieldTrackAmberDark,
    tertiary = FieldTrackAmber,
    onTertiary = FieldTrackNavy,
    background = SurfaceOffWhite,
    onBackground = TextPrimary,
    surface = SurfaceWhite,
    onSurface = TextPrimary,
    surfaceVariant = SurfaceContainer,
    onSurfaceVariant = TextMuted,
    outline = BorderMuted,
    error = ErrorRed,
    onError = SurfaceWhite
)

private val DarkColorScheme = darkColorScheme(
    primary = FieldTrackAmber,
    onPrimary = FieldTrackNavyDark,
    primaryContainer = FieldTrackNavyLight,
    onPrimaryContainer = SurfaceWhite,
    secondary = FieldTrackAmber,
    onSecondary = FieldTrackNavyDark,
    secondaryContainer = FieldTrackNavyLight,
    onSecondaryContainer = FieldTrackAmberLight,
    tertiary = FieldTrackAmber,
    onTertiary = FieldTrackNavyDark,
    background = FieldTrackNavyDark,
    onBackground = SurfaceWhite,
    surface = FieldTrackNavy,
    onSurface = SurfaceWhite,
    surfaceVariant = FieldTrackNavyLight,
    onSurfaceVariant = TextSubtle,
    outline = FieldTrackNavyLight,
    error = ErrorRed,
    onError = SurfaceWhite
)

@Composable
fun FieldTrackProTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit
) {
    val colorScheme = if (darkTheme) DarkColorScheme else LightColorScheme
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            window.statusBarColor = colorScheme.primary.toArgb()
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = !darkTheme
        }
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = Typography,
        content = content
    )
}
