package com.fieldtrackpro.android.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.googlefonts.Font
import androidx.compose.ui.text.googlefonts.GoogleFont
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.R

/**
 * FieldTrack Pro Centralized Brand Typography
 *
 * Primary Display/UI Font: League Spartan
 * Secondary/Readable Serif Font: Libre Baskerville
 */

val provider = GoogleFont.Provider(
    providerAuthority = "com.google.android.gms.fonts",
    providerPackage = "com.google.android.gms",
    certificates = R.array.com_google_android_gms_fonts_certs
)

val LeagueSpartanFont = GoogleFont("League Spartan")
val LibreBaskervilleFont = GoogleFont("Libre Baskerville")

val LeagueSpartanFamily = FontFamily(
    Font(googleFont = LeagueSpartanFont, fontProvider = provider, weight = FontWeight.Normal),
    Font(googleFont = LeagueSpartanFont, fontProvider = provider, weight = FontWeight.Medium),
    Font(googleFont = LeagueSpartanFont, fontProvider = provider, weight = FontWeight.SemiBold),
    Font(googleFont = LeagueSpartanFont, fontProvider = provider, weight = FontWeight.Bold)
)

val LibreBaskervilleFamily = FontFamily(
    Font(googleFont = LibreBaskervilleFont, fontProvider = provider, weight = FontWeight.Normal),
    Font(googleFont = LibreBaskervilleFont, fontProvider = provider, weight = FontWeight.Bold)
)

// Brand Typography Specification
val Typography = Typography(
    displayLarge = TextStyle(
        fontFamily = LeagueSpartanFamily,
        fontWeight = FontWeight.Bold,
        fontSize = 32.sp,
        lineHeight = 38.sp,
        letterSpacing = (-0.5).sp
    ),
    displayMedium = TextStyle(
        fontFamily = LeagueSpartanFamily,
        fontWeight = FontWeight.Bold,
        fontSize = 28.sp,
        lineHeight = 34.sp
    ),
    displaySmall = TextStyle(
        fontFamily = LeagueSpartanFamily,
        fontWeight = FontWeight.SemiBold,
        fontSize = 24.sp,
        lineHeight = 30.sp
    ),
    headlineLarge = TextStyle(
        fontFamily = LeagueSpartanFamily,
        fontWeight = FontWeight.Bold,
        fontSize = 22.sp,
        lineHeight = 28.sp
    ),
    headlineMedium = TextStyle(
        fontFamily = LeagueSpartanFamily,
        fontWeight = FontWeight.SemiBold,
        fontSize = 18.sp,
        lineHeight = 24.sp
    ),
    headlineSmall = TextStyle(
        fontFamily = LeagueSpartanFamily,
        fontWeight = FontWeight.Medium,
        fontSize = 16.sp,
        lineHeight = 22.sp
    ),
    titleLarge = TextStyle(
        fontFamily = LeagueSpartanFamily,
        fontWeight = FontWeight.Bold,
        fontSize = 18.sp,
        lineHeight = 24.sp
    ),
    titleMedium = TextStyle(
        fontFamily = LeagueSpartanFamily,
        fontWeight = FontWeight.SemiBold,
        fontSize = 15.sp,
        lineHeight = 20.sp
    ),
    titleSmall = TextStyle(
        fontFamily = LeagueSpartanFamily,
        fontWeight = FontWeight.Medium,
        fontSize = 13.sp,
        lineHeight = 18.sp
    ),
    bodyLarge = TextStyle(
        fontFamily = LeagueSpartanFamily,
        fontWeight = FontWeight.Normal,
        fontSize = 16.sp,
        lineHeight = 24.sp,
        letterSpacing = 0.15.sp
    ),
    bodyMedium = TextStyle(
        fontFamily = LeagueSpartanFamily,
        fontWeight = FontWeight.Normal,
        fontSize = 14.sp,
        lineHeight = 20.sp,
        letterSpacing = 0.25.sp
    ),
    bodySmall = TextStyle(
        fontFamily = LeagueSpartanFamily,
        fontWeight = FontWeight.Normal,
        fontSize = 12.sp,
        lineHeight = 16.sp,
        letterSpacing = 0.4.sp
    ),
    labelLarge = TextStyle(
        fontFamily = LeagueSpartanFamily,
        fontWeight = FontWeight.SemiBold,
        fontSize = 14.sp,
        lineHeight = 20.sp,
        letterSpacing = 0.1.sp
    ),
    labelMedium = TextStyle(
        fontFamily = LeagueSpartanFamily,
        fontWeight = FontWeight.Medium,
        fontSize = 12.sp,
        lineHeight = 16.sp,
        letterSpacing = 0.5.sp
    ),
    labelSmall = TextStyle(
        fontFamily = LeagueSpartanFamily,
        fontWeight = FontWeight.Medium,
        fontSize = 10.sp,
        lineHeight = 14.sp,
        letterSpacing = 0.5.sp
    )
)

// Readable Serif Typography Style for documents/notes
val SerifBodyStyle = TextStyle(
    fontFamily = LibreBaskervilleFamily,
    fontWeight = FontWeight.Normal,
    fontSize = 14.sp,
    lineHeight = 22.sp
)
