package com.fieldtrackpro.android.ui.theme

import androidx.compose.ui.graphics.Color

/**
 * FieldTrack Pro Centralized Brand Design System Tokens
 *
 * Official Palette Specification:
 * - Black:             #000000
 * - Primary Navy:      #14213D
 * - Accent Gold:       #FCA311
 * - Light Gray:        #E5E5E5
 * - White:             #FFFFFF
 *
 * Semantic Mappings:
 * - Success:           #10B981 (Green for verified/completed check-ins)
 * - Error:             #EF4444 (Red for violations/cancellations)
 * - Warning:           #FCA311 (Gold brand color)
 */

// 1. Official Core Palette
val BrandBlack = Color(0xFF000000)
val BrandNavy = Color(0xFF14213D)
val BrandNavyDark = Color(0xFF0B1426)
val BrandNavyLight = Color(0xFF1C2D52)

val BrandGold = Color(0xFFFCA311)
val BrandGoldDark = Color(0xFF8A5A00) // gold-ink: the only gold that is legible as text on light surfaces (≈6:1)
val BrandGoldLight = Color(0xFFFFF1D6)

val BrandLightGray = Color(0xFFE3E7EE) // navy-tinted hairline
val BrandWhite = Color(0xFFFFFFFF)

// 1b. Premium scale (design system v2, Nov 2026). Navy is the ground for one hero area per screen;
//     gold is a signal colour (primary CTA, active state, the mark) and is never used as text on light surfaces.
val Navy950 = Color(0xFF0B1426)
val Navy100 = Color(0xFFE8ECF4)
val Navy50 = Color(0xFFF3F5F9)
val Navy700Pressed = Color(0xFF2A3F6B)
val GoldOnNavyText = Color(0xFFFCC15A) // gold text on navy surfaces
val TextOnNavyMuted = Color(0xFFB4BDD0)

// 2. Semantic Surface & Background Tokens
val SurfacePrimary = BrandWhite
val SurfaceSecondary = Color(0xFFF5F6F9) // navy-tinted app background
val SurfaceTertiary = BrandLightGray
val SurfaceCard = BrandWhite

// 3. Typography Content Tokens
val TextPrimary = BrandNavy // #14213D (Bold & Primary UI)
val TextSecondary = Color(0xFF4B5670) // secondary text (≈7:1 on white)
val TextSubtle = Color(0xFF5B6680) // metadata, timestamps (≈5.7:1 on white)
val TextMuted = TextSubtle
val TextOnDark = BrandWhite
val TextOnGold = BrandBlack

// 4. Border Tokens
val BorderSubtle = BrandLightGray
val BorderFocused = BrandGold
val BorderActive = BrandNavy

// 5. Semantic Feedback Tokens
val SuccessGreen = Color(0xFF047857) // white text on it ≈5.5:1
val SuccessGreenBg = Color(0xFFE3F6EE)
val SuccessGreenText = Color(0xFF046C4E)

val ErrorRed = Color(0xFFC62828) // white text on it ≈5.6:1
val ErrorRedBg = Color(0xFFFDECEC)
val ErrorRedText = Color(0xFF991B1B)

val WarningGold = Color(0xFFB45309) // warning amber, deliberately distinct from brand gold
val WarningGoldBg = Color(0xFFFEF3E2)
val WarningGoldText = Color(0xFF8A4B08)

// 6. Compatibility & Legacy Bridges
val FieldTrackNavy = BrandNavy
val FieldTrackNavyDark = BrandNavyDark
val FieldTrackNavyLight = BrandNavyLight
val FieldTrackAmber = BrandGold
val FieldTrackAmberDark = BrandGoldDark
val FieldTrackAmberLight = BrandGoldLight
val SurfaceWhite = BrandWhite
val SurfaceOffWhite = SurfaceSecondary
val SurfaceContainer = Color(0xFFEEF1F6)
val BorderMuted = BrandLightGray
val SuccessGreenLight = SuccessGreenBg
val WarningAmber = BrandGold
val WarningAmberLight = BrandGoldLight
val ErrorRedLight = ErrorRedBg
val Navy900 = BrandNavyDark
val Navy800 = BrandNavy
val Navy700 = BrandNavyLight
val Slate900 = BrandNavy
val Slate800 = BrandNavyLight
val Slate700 = TextSecondary
val Slate500 = TextSecondary
val Slate300 = TextSubtle
val Slate100 = BrandLightGray
val Slate50 = SurfaceSecondary
val ElectricBlue = BrandNavy
val ElectricBlueLight = BrandNavyLight
val ElectricBlueDark = BrandNavyDark
val EmeraldGreen = SuccessGreen
val EmeraldGreenLight = SuccessGreenBg
val AmberWarning = BrandGold
val CoralRed = ErrorRed
val PrimaryButton = BrandNavy
val AccentButton = BrandGold
