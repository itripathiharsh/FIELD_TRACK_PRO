package com.fieldtrackpro.android.data.remote

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Unit tests for Centralized Error Handling (APP-ERR-001 & APP-ERR-002).
 */
class ApiErrorParserTest {

    @Test
    fun parsesStructuredBackendErrorEnvelope() {
        val errorJson = """
            {
                "error": {
                    "code": "OUTLET_CODE_EXISTS",
                    "message": "A customer with DMS Code 'OUT-123' already exists.",
                    "details": []
                }
            }
        """.trimIndent()

        val parsed = ApiErrorParser.parse(409, errorJson)
        assertEquals("OUTLET_CODE_EXISTS", parsed.code)
        assertEquals("A customer with DMS Code 'OUT-123' already exists.", parsed.message)
        assertEquals(409, parsed.httpStatus)
    }

    @Test
    fun handlesNullOrEmptyErrorBodyWithCuratedDefault() {
        val parsed401 = ApiErrorParser.parse(401, null)
        assertEquals("Session expired. Please sign in again.", parsed401.message)

        val parsed403 = ApiErrorParser.parse(403, "")
        assertEquals("You are not assigned to this visit/customer.", parsed403.message)

        val parsed404 = ApiErrorParser.parse(404, "   ")
        assertEquals("Visit or customer not found. It may have been reassigned.", parsed404.message)

        val parsed429 = ApiErrorParser.parse(429, null)
        assertEquals("Too many attempts. Please wait and try again.", parsed429.message)

        val parsed500 = ApiErrorParser.parse(500, null)
        assertEquals("Server is temporarily unavailable. Please try again shortly.", parsed500.message)
    }

    @Test
    fun sanitizesRawJsonSoUsersNeverSeeJsonSyntax() {
        val rawJson = """{"detail":"Internal raw exception dump"}"""
        val parsed = ApiErrorParser.parse(500, rawJson)
        // Ensure user message is friendly and never contains braces
        assertTrue(!parsed.message.startsWith("{"))
        assertTrue(!parsed.message.contains("\"detail\""))
    }
}
