package com.fieldtrackpro.android

import com.fieldtrackpro.android.workers.UploadRetryPolicy
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class UploadRetryPolicyTest {

    @Test
    fun networkAndServerErrors_areTransient() {
        assertTrue(UploadRetryPolicy.isTransientFailure("Network error: timeout"))
        assertTrue(UploadRetryPolicy.isTransientFailure("Signature upload failed (503): Service Unavailable"))
    }

    @Test
    fun validationAndAuthFailures_areNotTransient() {
        assertFalse(UploadRetryPolicy.isTransientFailure("Signature upload failed (400): invalid image"))
        assertFalse(UploadRetryPolicy.isTransientFailure("Signature upload failed (400): unsupported content type"))
        assertFalse(UploadRetryPolicy.isTransientFailure("Signature upload failed (413): too large"))
        assertFalse(UploadRetryPolicy.isTransientFailure("Signature upload failed (401): unauthorized"))
        assertFalse(UploadRetryPolicy.isTransientFailure("Signature upload failed (403): forbidden"))
    }

    @Test
    fun alreadyExists_isNotTransient() {
        // A race between a successful direct upload and a still-pending
        // safety-net retry surfaces as SIGNATURE_ALREADY_EXISTS - that's a
        // safe no-op, not something worth retrying.
        assertFalse(UploadRetryPolicy.isTransientFailure("Signature upload failed (409): signature already exists"))
    }
}
