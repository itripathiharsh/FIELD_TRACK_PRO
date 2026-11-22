package com.fieldtrackpro.android.utils

import java.math.BigDecimal
import java.math.RoundingMode

/**
 * Indian-rupee formatting with lakh/crore grouping (₹1,25,000 / ₹1,25,00,000.50).
 *
 * Implemented by hand because java.text.DecimalFormat only supports uniform grouping (JVM unit tests would render
 * 125,000) and the dashboard used to call toInt(), which silently dropped paise.
 *
 * Paise are always kept: an amount with paise prints two decimals, a whole-rupee amount prints none unless
 * [alwaysShowPaise] is set.
 */
object MoneyFormat {

    fun inr(amount: Double?, alwaysShowPaise: Boolean = false): String {
        if (amount == null || amount.isNaN() || amount.isInfinite()) return "₹0"
        return inr(BigDecimal.valueOf(amount), alwaysShowPaise)
    }

    fun inr(amount: BigDecimal, alwaysShowPaise: Boolean = false): String {
        val rounded = amount.setScale(2, RoundingMode.HALF_UP)
        val negative = rounded.signum() < 0
        val abs = rounded.abs()
        val rupees = abs.setScale(0, RoundingMode.DOWN)
        val paise = abs.subtract(rupees).movePointRight(2).toInt()
        val grouped = groupIndian(rupees.toPlainString())
        val body = if (paise != 0 || alwaysShowPaise) "$grouped.${paise.toString().padStart(2, '0')}" else grouped
        return (if (negative) "-₹" else "₹") + body
    }

    /** Parses a decimal API string ("12500.50"); blank or malformed -> null. */
    fun parse(value: String?): BigDecimal? = value?.trim()?.takeIf { it.isNotEmpty() }?.toBigDecimalOrNull()

    internal fun groupIndian(digits: String): String {
        if (digits.length <= 3) return digits
        val last3 = digits.takeLast(3)
        val rest = digits.dropLast(3)
        val pairs = rest.reversed().chunked(2).joinToString(",").reversed()
        return "$pairs,$last3"
    }
}
