package com.fieldtrackpro.android.phase4

import com.fieldtrackpro.android.data.model.BrandAllocationInput
import com.fieldtrackpro.android.data.model.BrandSummaryDto
import com.fieldtrackpro.android.utils.PaymentBrandRules
import org.junit.Assert.*
import org.junit.Test

class PaymentBrandRulesTest {
    private fun row(b: String, out: String = "100") = BrandSummaryDto(brand = b, totalInvoiced = out, totalPaid = "0", totalOutstanding = out)
    private val registered = listOf("Accessories", "Mobiles")

    @Test fun activeBrandsAreAllocatable() {
        val r = PaymentBrandRules.rows(listOf(row("accessories"), row("Mobiles")), registered)
        assertEquals(listOf("Accessories", "Mobiles"), r.allocatable.map { it.brand })
        assertTrue(r.hasAllocatableBrand)
    }

    @Test fun syntheticUnbrandedIsNeverAllocatable() {
        val r = PaymentBrandRules.rows(listOf(row("Accessories"), row("Unbranded", "500")), registered)
        assertEquals(listOf("Accessories"), r.allocatable.map { it.brand })
        assertEquals(500.0, r.notAllocatableOutstanding, 0.001)
    }

    @Test fun emptyBrandListMeansNothingAllocatable() {
        val r = PaymentBrandRules.rows(listOf(row("Unbranded")), registered)
        assertFalse(r.hasAllocatableBrand)
        assertFalse(PaymentBrandRules.rows(listOf(row("Mobiles")), emptyList()).hasAllocatableBrand)
    }

    @Test fun unknownBrandRejectedBeforeSubmit() {
        val msg = PaymentBrandRules.validate(listOf(BrandAllocationInput("Unbranded", 10.0)), 10.0, registered)
        assertNotNull(msg); assertTrue(msg!!.contains("Unbranded"))
    }

    @Test fun allocationMismatchRejected() {
        val msg = PaymentBrandRules.validate(listOf(BrandAllocationInput("Mobiles", 10.0)), 25.0, registered)
        assertNotNull(msg)
    }

    @Test fun multiBrandValidPasses() {
        val a = listOf(BrandAllocationInput("Mobiles", 60000.0), BrandAllocationInput("Accessories", 20000.0))
        assertNull(PaymentBrandRules.validate(a, 80000.0, registered))
    }

    @Test fun emptyZeroAndPaiseRules() {
        assertNotNull(PaymentBrandRules.validate(emptyList(), 0.0, registered))
        assertNotNull(PaymentBrandRules.validate(listOf(BrandAllocationInput("Mobiles", 0.0)), 0.0, registered))
        assertNotNull(PaymentBrandRules.validate(listOf(BrandAllocationInput("Mobiles", 1.234)), 1.234, registered))
    }

    @Test fun friendlyMessages() {
        val raw = """{"error":{"code":"UNKNOWN_BRAND","message":"Brand 'Unbranded' does not exist"}}"""
        val m = PaymentBrandRules.friendlyServerMessage(422, raw, "fallback")
        assertFalse(m.contains("{")); assertTrue(m.contains("Unbranded"))
        assertEquals("fallback", PaymentBrandRules.friendlyServerMessage(403, raw, "fallback"))
        assertEquals("fallback", PaymentBrandRules.friendlyServerMessage(500, raw, "fallback"))
    }
}
