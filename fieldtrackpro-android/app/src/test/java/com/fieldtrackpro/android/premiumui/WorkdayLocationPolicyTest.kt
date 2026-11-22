package com.fieldtrackpro.android.premiumui

import com.fieldtrackpro.android.utils.WorkdayLocationPolicy
import com.fieldtrackpro.android.utils.WorkdayLocationPolicy.Decision
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class WorkdayLocationPolicyTest {
    private fun reject(lat: Double?, lon: Double?, acc: Double? = 10.0, mock: Boolean = false) =
        WorkdayLocationPolicy.evaluate(lat, lon, acc, mock) is Decision.Reject

    @Test fun nullIslandAndMissingFixesAreRejected() {
        assertTrue(reject(0.0, 0.0)) // the old End Day fallback
        assertTrue(reject(null, 80.33))
        assertTrue(reject(26.45, null))
        assertTrue(reject(Double.NaN, 80.33))
        assertTrue(reject(95.0, 80.33)) // out of range
    }

    @Test fun mockAndVagueFixesAreRejected() {
        assertTrue(reject(26.45, 80.33, mock = true))
        assertTrue(reject(26.45, 80.33, acc = null))
        assertTrue(reject(26.45, 80.33, acc = -1.0))
        assertTrue(reject(26.45, 80.33, acc = WorkdayLocationPolicy.MAX_ACCURACY_M + 1))
    }

    @Test fun goodFixIsAccepted() {
        assertEquals(Decision.Accept(26.4499, 80.3319, 35.0), WorkdayLocationPolicy.evaluate(26.4499, 80.3319, 35.0, false))
        assertTrue(WorkdayLocationPolicy.evaluate(26.45, 80.33, WorkdayLocationPolicy.MAX_ACCURACY_M, false) is Decision.Accept)
    }

    @Test fun submittableGuard() {
        assertFalse(WorkdayLocationPolicy.isSubmittable(0.0, 0.0))
        assertFalse(WorkdayLocationPolicy.isSubmittable(Double.NaN, 1.0))
        assertTrue(WorkdayLocationPolicy.isSubmittable(26.45, 80.33))
    }
}
