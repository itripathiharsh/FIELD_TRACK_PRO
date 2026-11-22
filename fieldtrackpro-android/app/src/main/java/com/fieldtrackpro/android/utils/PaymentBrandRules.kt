package com.fieldtrackpro.android.utils

import com.fieldtrackpro.android.data.model.BrandAllocationInput
import com.fieldtrackpro.android.data.model.BrandSummaryDto
import com.fieldtrackpro.android.data.remote.ApiErrorParser
import java.util.Locale
import kotlin.math.abs

/**
 * Brand rules for a field collection.
 *
 * ROOT CAUSE of "UNKNOWN_BRAND: Brand 'Unbranded' does not exist":
 * the outlet account (GET /customers/{id}/account) returns one `brand_summary` row per brand AND, when a Tally ledger
 * has an unallocated balance or on-account bills, a synthetic "Unbranded" row (see account_position.py). It is a
 * display bucket, not a registered brand. The payment screen drew an input for every summary row and submitted every
 * non-zero amount, so an amount typed against "Unbranded" reached POST /payments, whose brand allocation is validated
 * against the real brand list (brand_service.validate_brand_for_transaction) and was rejected with 422 UNKNOWN_BRAND.
 *
 * Fix: only brands that exist in the authorized backend brand list (GET /brands, active only) can be allocated.
 * Summary rows that are not real brands are shown as information, never as an input; nothing is invented or created.
 */
object PaymentBrandRules {

    data class Rows(
        /** Summary rows that are real, active brands (name normalised to the registered spelling). */
        val allocatable: List<BrandSummaryDto>,
        /** Summary rows that are not registered brands (e.g. the synthetic "Unbranded" bucket). */
        val notAllocatable: List<BrandSummaryDto>,
        /** Outstanding sitting in rows that cannot be allocated to a brand (shown as a note). */
        val notAllocatableOutstanding: Double
    ) {
        val hasAllocatableBrand: Boolean get() = allocatable.isNotEmpty()
    }

    fun norm(name: String?): String = (name ?: "").trim().lowercase(Locale.ROOT).replace(Regex("\\s+"), " ")

    fun rows(summary: List<BrandSummaryDto>, registeredBrands: List<String>): Rows {
        val byNorm = registeredBrands.associateBy { norm(it) }
        val ok = ArrayList<BrandSummaryDto>()
        val rest = ArrayList<BrandSummaryDto>()
        val seen = HashSet<String>()
        for (row in summary) {
            val canonical = byNorm[norm(row.brand)]
            if (canonical != null && seen.add(norm(canonical))) ok += row.copy(brand = canonical) else if (canonical == null) rest += row
        }
        val outstanding = rest.sumOf { it.totalOutstanding.toDoubleOrNull() ?: 0.0 }.coerceAtLeast(0.0)
        return Rows(ok, rest, outstanding)
    }

    /** Null when the allocations are valid for [total]; otherwise a message the employee can act on. */
    fun validate(allocations: List<BrandAllocationInput>, total: Double, registeredBrands: List<String>): String? {
        if (allocations.isEmpty()) return "Enter an amount against at least one brand."
        val allowed = registeredBrands.map { norm(it) }.toSet()
        for (a in allocations) {
            if (norm(a.brand) !in allowed) return "\"${a.brand}\" is not a registered brand, so money cannot be allocated to it. Ask your administrator."
            if (a.amount.isNaN() || a.amount <= 0.0) return "Enter an amount above zero for ${a.brand}."
            if (abs(a.amount * 100 - Math.round(a.amount * 100)) > 1e-6) return "${a.brand}: use at most 2 decimal places (paise)."
        }
        val sum = allocations.sumOf { it.amount }
        if (abs(sum - total) > 0.005) {
            return "The brand amounts add up to ${MoneyFormat.inr(sum, alwaysShowPaise = true)} but the total is ${MoneyFormat.inr(total, alwaysShowPaise = true)}. Please correct the amounts."
        }
        return null
    }

    /** Human message for a rejected collection: no raw JSON, brand problems explained. [fallback] is returned unchanged for other codes. */
    fun friendlyServerMessage(httpCode: Int, rawBody: String?, fallback: String): String {
        // 403 PASSWORD_CHANGE_REQUIRED and similar are recognised elsewhere from the original text: keep it intact.
        if (httpCode == 403 || httpCode >= 500 || httpCode == 401) return fallback
        val parsed = ApiErrorParser.parse(httpCode, rawBody)
        val brand = Regex("Brand '([^']+)'").find(parsed.message)?.groupValues?.get(1)
        return when (parsed.code) {
            "UNKNOWN_BRAND" ->
                "The brand \"${brand ?: "selected"}\" is not set up in FieldTrack, so this collection was not saved. Ask your administrator to add it."
            "INACTIVE_BRAND" ->
                "The brand \"${brand ?: "selected"}\" is switched off, so this collection was not saved. Ask your administrator."
            else -> parsed.message.takeIf { it.isNotBlank() && httpCode in 400..499 } ?: fallback
        }
    }
}
