package com.fieldtrackpro.android.utils

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class DateTimeUtilsTest {

    @Test
    fun testFormatDisplayDateTime_validIsoString() {
        val iso = "2026-08-27T10:30:00Z"
        val formatted = DateTimeUtils.formatDisplayDateTime(iso)
        assertNotNull(formatted)
        assertTrue(formatted.contains("2026") || formatted.contains("Aug") || formatted.contains("08"))
    }

    @Test
    fun testFormatDisplayDateTime_nullOrBlankReturnsNa() {
        assertEquals("N/A", DateTimeUtils.formatDisplayDateTime(null))
        assertEquals("N/A", DateTimeUtils.formatDisplayDateTime(""))
        assertEquals("N/A", DateTimeUtils.formatDisplayDateTime("   "))
    }

    @Test
    fun testFormatDisplayDate_validIsoString() {
        val iso = "2026-08-27T10:30:00Z"
        val formatted = DateTimeUtils.formatDisplayDate(iso)
        assertNotNull(formatted)
        assertTrue(formatted.contains("2026"))
    }

    @Test
    fun testFormatEpochMillis() {
        val millis = 1756285200000L // 2025/2026 epoch timestamp
        val formatted = DateTimeUtils.formatEpochMillis(millis)
        assertNotNull(formatted)
        assertTrue(formatted.isNotEmpty())
    }

    @Test
    fun testUtcToIstConversion_exactHour() {
        // 10:00 UTC is 15:30 (03:30 PM) IST (+05:30)
        val iso = "2026-08-27T10:00:00Z"
        val formatted = DateTimeUtils.formatDisplayDateTime(iso)
        assertTrue("Formatted IST output '$formatted' should contain '03:30 pm' or '03:30 PM'", formatted.contains("03:30 pm", ignoreCase = true))
    }
}
