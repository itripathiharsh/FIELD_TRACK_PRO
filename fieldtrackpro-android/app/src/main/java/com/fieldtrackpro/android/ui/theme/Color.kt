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
val BrandNavyDark = Color(0xFF0A1120)
val BrandNavyLight = Color(0xFF1E2F54)

val BrandGold = Color(0xFFFCA311)
val BrandGoldDark = Color(0xFFE5920A)
val BrandGoldLight = Color(0xFFFFF4DE)

val BrandLightGray = Color(0xFFE5E5E5)
val BrandWhite = Color(0xFFFFFFFF)

// 2. Semantic Surface & Background Tokens
val SurfacePrimary = BrandWhite
val SurfaceSecondary = Color(0xFFF8F9FA) // Clean off-white surface
val SurfaceTertiary = BrandLightGray
val SurfaceCard = BrandWhite

// 3. Typography Content Tokens
val TextPrimary = BrandNavy // #14213D (Bold & Primary UI)
val TextSecondary = Color(0xFF2B3A4A) // Dark Muted Navy-Gray (High readability normal body/descriptions)
val TextSubtle = Color(0xFF4B5563) // Accessible Slate Gray (Metadata, timestamps, subheadings)
val TextMuted = TextSubtle
val TextOnDark = BrandWhite
val TextOnGold = BrandBlack

// 4. Border Tokens
val BorderSubtle = BrandLightGray
val BorderFocused = BrandGold
val BorderActive = BrandNavy

// 5. Semantic Feedback Tokens
val SuccessGreen = Color(0xFF10B981)
val SuccessGreenBg = Color(0xFFD1FAE5)
val SuccessGreenText = Color(0xFF065F46)

val ErrorRed = Color(0xFFEF4444)
val ErrorRedBg = Color(0xFFFEE2E2)
val ErrorRedText = Color(0xFF991B1B)

val WarningGold = BrandGold
val WarningGoldBg = BrandGoldLight
val WarningGoldText = Color(0xFF78350F)

// 6. Compatibility & Legacy Bridges
val FieldTrackNavy = BrandNavy
val FieldTrackNavyDark = BrandNavyDark
val FieldTrackNavyLight = BrandNavyLight
val FieldTrackAmber = BrandGold
val FieldTrackAmberDark = BrandGoldDark
val FieldTrackAmberLight = BrandGoldLight
val SurfaceWhite = BrandWhite
val SurfaceOffWhite = SurfaceSecondary
val SurfaceContainer = Color(0xFFF0F1F3)
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
