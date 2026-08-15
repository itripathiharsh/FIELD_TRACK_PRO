package com.fieldtrackpro.android.data.api

import com.fieldtrackpro.android.data.model.SignatureCreateRequest
import com.fieldtrackpro.android.data.model.SignatureDto
import org.junit.Assert.assertEquals
import org.junit.Test

class SignatureCreateRequestTest {

    @Test
    fun signatureCreateRequest_fieldsCorrect() {
        val request = SignatureCreateRequest(
            signatureType = "EMPLOYEE",
            signatureImageBase64 = "base64encodeddata"
        )

        assertEquals("EMPLOYEE", request.signatureType)
        assertEquals("base64encodeddata", request.signatureImageBase64)
    }

    @Test
    fun signatureCreateRequest_customerType() {
        val request = SignatureCreateRequest(
            signatureType = "CUSTOMER",
            signatureImageBase64 = "iVBORkg=="
        )

        assertEquals("CUSTOMER", request.signatureType)
    }

    @Test
    fun signatureDto_typesCorrect() {
        val employeeSig = SignatureDto(
            id = "sig-1",
            visitId = "visit-1",
            signatureType = "EMPLOYEE",
            storageKey = "visits/visit-1/employee.png",
            signedAt = "2026-01-01T10:00:00Z"
        )

        val customerSig = SignatureDto(
            id = "sig-2",
            visitId = "visit-1",
            signatureType = "CUSTOMER",
            storageKey = "visits/visit-1/customer.png",
            signedAt = "2026-01-01T10:05:00Z"
        )

        assertEquals(true, employeeSig.isEmployee)
        assertEquals(false, employeeSig.isCustomer)
        assertEquals(false, customerSig.isEmployee)
        assertEquals(true, customerSig.isCustomer)
    }
}
