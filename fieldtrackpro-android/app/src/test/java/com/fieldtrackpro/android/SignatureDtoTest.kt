package com.fieldtrackpro.android

import com.fieldtrackpro.android.data.model.SignatureDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SignatureDtoTest {

    @Test
    fun signatureDto_employeeType() {
        val sig = SignatureDto(
            id = "123",
            visitId = "v456",
            signatureType = "EMPLOYEE",
            storageKey = "signatures/v456/123.png",
            signedAt = "2026-01-01T00:00:00"
        )
        assertTrue("Should be employee signature", sig.isEmployee)
        assertFalse("Should not be customer signature", sig.isCustomer)
    }

    @Test
    fun signatureDto_customerType() {
        val sig = SignatureDto(
            id = "123",
            visitId = "v456",
            signatureType = "CUSTOMER",
            storageKey = "signatures/v456/123.png",
            signedAt = "2026-01-01T00:00:00"
        )
        assertFalse("Should not be employee signature", sig.isEmployee)
        assertTrue("Should be customer signature", sig.isCustomer)
    }

    @Test
    fun signatureDto_fieldsCorrect() {
        val sig = SignatureDto(
            id = "sig-123",
            visitId = "visit-456",
            signatureType = "EMPLOYEE",
            storageKey = "signatures/visit-456/sig-123.png",
            signedAt = "2026-01-01T10:00:00"
        )
        assertEquals("sig-123", sig.id)
        assertEquals("visit-456", sig.visitId)
        assertEquals("EMPLOYEE", sig.signatureType)
        assertEquals("signatures/visit-456/sig-123.png", sig.storageKey)
        assertEquals("2026-01-01T10:00:00", sig.signedAt)
    }
}
