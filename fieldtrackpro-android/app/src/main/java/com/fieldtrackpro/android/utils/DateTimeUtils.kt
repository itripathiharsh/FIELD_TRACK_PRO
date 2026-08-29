package com.fieldtrackpro.android.utils

import java.text.SimpleDateFormat
import java.time.Instant
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/**
 * Project-wide date and timestamp formatter.
 *
 * APP-ATT-013: Formats raw ISO-8601 strings explicitly in Asia/Kolkata (IST, UTC+05:30)
 * to maintain consistent presentation with the backend and web application.
 */
object DateTimeUtils {

    val IST_ZONE: ZoneId = ZoneId.of("Asia/Kolkata")
    private val IST_TIMEZONE: TimeZone = TimeZone.getTimeZone("Asia/Kolkata")

    private val displayDateTimeFormatter: DateTimeFormatter =
        DateTimeFormatter.ofPattern("dd MMM yyyy, hh:mm a", Locale.ENGLISH)

    private val displayDateFormatter: DateTimeFormatter =
        DateTimeFormatter.ofPattern("dd MMM yyyy", Locale.ENGLISH)

    private val displayTimeFormatter: DateTimeFormatter =
        DateTimeFormatter.ofPattern("hh:mm a", Locale.ENGLISH)

    /**
     * Formats an ISO-8601 string (e.g. "2026-08-27T14:30:00Z") to "dd MMM yyyy, hh:mm a" in IST.
     */
    fun formatDisplayDateTime(isoString: String?): String {
        if (isoString.isNullOrBlank()) return "N/A"
        val nonNullIso: String = isoString
        return try {
            val zdt = parseToZonedDateTime(nonNullIso)
            zdt.withZoneSameInstant(IST_ZONE).format(displayDateTimeFormatter)
        } catch (e: Exception) {
            tryFallbackFormatting(nonNullIso, "dd MMM yyyy, hh:mm a") ?: nonNullIso
        }
    }

    /**
     * Formats an ISO-8601 string to "dd MMM yyyy" in IST.
     */
    fun formatDisplayDate(isoString: String?): String {
        if (isoString.isNullOrBlank()) return "N/A"
        val nonNullIso: String = isoString
        return try {
            val zdt = parseToZonedDateTime(nonNullIso)
            zdt.withZoneSameInstant(IST_ZONE).format(displayDateFormatter)
        } catch (e: Exception) {
            tryFallbackFormatting(nonNullIso, "dd MMM yyyy") ?: nonNullIso
        }
    }

    /**
     * Formats an ISO-8601 string to "hh:mm a" in IST.
     */
    fun formatDisplayTime(isoString: String?): String {
        if (isoString.isNullOrBlank()) return "N/A"
        val nonNullIso: String = isoString
        return try {
            val zdt = parseToZonedDateTime(nonNullIso)
            zdt.withZoneSameInstant(IST_ZONE).format(displayTimeFormatter)
        } catch (e: Exception) {
            tryFallbackFormatting(nonNullIso, "hh:mm a") ?: nonNullIso
        }
    }

    /**
     * Formats epoch milliseconds to "dd MMM yyyy, hh:mm a" in IST.
     */
    fun formatEpochMillis(millis: Long): String {
        return try {
            val instant = Instant.ofEpochMilli(millis)
            val zdt = instant.atZone(IST_ZONE)
            zdt.format(displayDateTimeFormatter)
        } catch (e: Exception) {
            val sdf = SimpleDateFormat("dd MMM yyyy, hh:mm a", Locale.ENGLISH)
            sdf.timeZone = IST_TIMEZONE
            sdf.format(Date(millis))
        }
    }

    private fun parseToZonedDateTime(isoString: String): ZonedDateTime {
        val trimmed = isoString.trim()
        return try {
            ZonedDateTime.parse(trimmed)
        } catch (e: Exception) {
            try {
                Instant.parse(trimmed).atZone(IST_ZONE)
            } catch (e2: Exception) {
                val ldt = java.time.LocalDateTime.parse(trimmed.replace(" ", "T"))
                ldt.atZone(IST_ZONE)
            }
        }
    }

    private fun tryFallbackFormatting(dateStr: String, targetPattern: String): String? {
        val patterns = listOf(
            "yyyy-MM-dd'T'HH:mm:ss",
            "yyyy-MM-dd HH:mm:ss",
            "yyyy-MM-dd",
            "yyyy-MM-dd'T'HH:mm:ss.SSS"
        )
        for (pattern in patterns) {
            try {
                val parser = SimpleDateFormat(pattern, Locale.US)
                parser.timeZone = TimeZone.getTimeZone("UTC")
                val date = parser.parse(dateStr)
                if (date != null) {
                    val formatter = SimpleDateFormat(targetPattern, Locale.ENGLISH)
                    formatter.timeZone = IST_TIMEZONE
                    return formatter.format(date)
                }
            } catch (e: Exception) {
                // Continue trying patterns
            }
        }
        return null
    }
}
