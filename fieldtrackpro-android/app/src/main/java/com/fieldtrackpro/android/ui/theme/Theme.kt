package com.fieldtrackpro.android.ui.theme

import android.app.Activity
import android.os.Build
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
    primary = ElectricBlue,
    onPrimary = SurfaceWhite,
    primaryContainer = Slate100,
    onPrimaryContainer = Slate900,
    secondary = EmeraldGreen,
    onSecondary = SurfaceWhite,
    tertiary = AmberWarning,
    background = Slate50,
    onBackground = Slate900,
    surface = SurfaceWhite,
    onSurface = Slate900,
    surfaceVariant = Slate100,
    onSurfaceVariant = Slate700,
    error = CoralRed,
    onError = SurfaceWhite
)

private val DarkColorScheme = darkColorScheme(
    primary = ElectricBlueLight,
    onPrimary = Slate900,
    primaryContainer = Slate800,
    onPrimaryContainer = Slate100,
    secondary = EmeraldGreenLight,
    onSecondary = Slate900,
    tertiary = AmberWarning,
    background = Slate900,
    onBackground = Slate50,
    surface = Slate800,
    onSurface = Slate50,
    surfaceVariant = Slate700,
    onSurfaceVariant = Slate300,
    error = CoralRed,
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
