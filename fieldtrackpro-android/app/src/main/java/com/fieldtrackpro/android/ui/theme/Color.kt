package com.fieldtrackpro.android.ui.theme

import androidx.compose.ui.graphics.Color

/**
 * FieldTrack Pro Centralized Brand Palette
 *
 * Source of Truth: Web Application Brand Architecture
 * - Primary Navy: #14213D
 * - Primary Amber: #FCA311
 * - Supporting Neutrals: Off-white surfaces, dark navy text, muted slate text, borders
 */

// Core Brand Colors
val FieldTrackNavy = Color(0xFF14213D)
val FieldTrackNavyDark = Color(0xFF0D1627)
val FieldTrackNavyLight = Color(0xFF1E2E52)

val FieldTrackAmber = Color(0xFFFCA311)
val FieldTrackAmberDark = Color(0xFFE5920A)
val FieldTrackAmberLight = Color(0xFFFFF3D6)

// Neutrals & Surfaces
val SurfaceWhite = Color(0xFFFFFFFF)
val SurfaceOffWhite = Color(0xFFF8FAFC)
val SurfaceContainer = Color(0xFFF1F5F9)
val SurfaceCard = Color(0xFFFFFFFF)

// Text & Content Tokens
val TextPrimary = Color(0xFF14213D)
val TextMuted = Color(0xFF64748B)
val TextSubtle = Color(0xFF94A3B8)
val BorderMuted = Color(0xFFE2E8F0)

// Semantic State Colors
val SuccessGreen = Color(0xFF10B981)
val SuccessGreenLight = Color(0xFFD1FAE5)
val WarningAmber = Color(0xFFFCA311)
val WarningAmberLight = Color(0xFFFEF3C7)
val ErrorRed = Color(0xFFEF4444)
val ErrorRedLight = Color(0xFFFEE2E2)

// Legacy Palette Bridges (Re-mapped to Brand Palette to prevent broken references)
val Navy900 = FieldTrackNavyDark
val Navy800 = FieldTrackNavy
val Navy700 = FieldTrackNavyLight

val Slate900 = FieldTrackNavy
val Slate800 = FieldTrackNavyLight
val Slate700 = Color(0xFF334155)
val Slate500 = TextMuted
val Slate300 = TextSubtle
val Slate100 = SurfaceContainer
val Slate50 = SurfaceOffWhite

val ElectricBlue = FieldTrackNavy
val ElectricBlueLight = FieldTrackNavyLight
val ElectricBlueDark = FieldTrackNavyDark

val EmeraldGreen = SuccessGreen
val EmeraldGreenLight = SuccessGreenLight

val AmberWarning = FieldTrackAmber
val CoralRed = ErrorRed

val PrimaryButton = FieldTrackNavy
val AccentButton = FieldTrackAmber
