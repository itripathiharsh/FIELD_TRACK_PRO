package com.fieldtrackpro.android.premiumui

import com.fieldtrackpro.android.utils.MoneyFormat
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.math.BigDecimal

class MoneyFormatTest {
    @Test fun indianGrouping() {
        assertEquals("₹0", MoneyFormat.inr(0.0))
        assertEquals("₹999", MoneyFormat.inr(999.0))
        assertEquals("₹1,000", MoneyFormat.inr(1000.0))
        assertEquals("₹1,25,000", MoneyFormat.inr(125000.0))
        assertEquals("₹12,34,567", MoneyFormat.inr(1234567.0))
        assertEquals("₹1,25,00,000", MoneyFormat.inr(12500000.0))
    }

    @Test fun paiseAreKeptNotTruncated() {
        // The dashboard used toInt(): 1250.75 rendered as ₹1250.
        assertEquals("₹1,250.75", MoneyFormat.inr(1250.75))
        assertEquals("₹0.50", MoneyFormat.inr(0.5))
        assertEquals("₹1,00,000.05", MoneyFormat.inr(100000.05))
        assertEquals("₹1,250.00", MoneyFormat.inr(1250.0, alwaysShowPaise = true))
    }

    @Test fun roundsHalfUpToPaise() {
        assertEquals("₹10.01", MoneyFormat.inr(BigDecimal("10.005")))
        assertEquals("₹10", MoneyFormat.inr(BigDecimal("9.999")))
    }

    @Test fun negativeAndInvalid() {
        assertEquals("-₹1,500", MoneyFormat.inr(-1500.0))
        assertEquals("₹0", MoneyFormat.inr(null as Double?))
        assertEquals("₹0", MoneyFormat.inr(Double.NaN))
    }

    @Test fun parsesApiDecimalStrings() {
        assertEquals("₹12,500.50", MoneyFormat.inr(MoneyFormat.parse("12500.50")!!))
        assertNull(MoneyFormat.parse(""))
        assertNull(MoneyFormat.parse("abc"))
    }
}
