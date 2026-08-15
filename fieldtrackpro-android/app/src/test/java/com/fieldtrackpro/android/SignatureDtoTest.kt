package com.fieldtrackpro.android

import com.fieldtrackpro.android.data.model.SignatureDto
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SignatureDtoTest {

    private fun dto(
        signatureType: String = "CUSTOMER",
        captureMethod: String = "SIGNATURE",
        supersededAt: String? = null,
    ) = SignatureDto(
        id = "sig-1",
        visitId = "visit-1",
        signatureType = signatureType,
        captureMethod = captureMethod,
        storageKey = "key",
        contentType = "image/png",
        fileSizeBytes = 123L,
        createdBy = "user-1",
        signedAt = "2026-01-01T00:00:00Z",
        supersededAt = supersededAt,
    )

    @Test
    fun isPhotoUpload_trueOnlyForPhotoUploadCaptureMethod() {
        assertTrue(dto(captureMethod = "PHOTO_UPLOAD").isPhotoUpload)
        assertFalse(dto(captureMethod = "SIGNATURE").isPhotoUpload)
    }

    @Test
    fun isSuperseded_trueOnlyWhenSupersededAtIsSet() {
        assertTrue(dto(supersededAt = "2026-01-02T00:00:00Z").isSuperseded)
        assertFalse(dto(supersededAt = null).isSuperseded)
    }

    @Test
    fun isEmployeeAndIsCustomer_matchSignatureType() {
        assertTrue(dto(signatureType = "EMPLOYEE").isEmployee)
        assertFalse(dto(signatureType = "EMPLOYEE").isCustomer)
        assertTrue(dto(signatureType = "CUSTOMER").isCustomer)
        assertFalse(dto(signatureType = "CUSTOMER").isEmployee)
    }
}
