package com.fieldtrackpro.android.phase3

import com.fieldtrackpro.android.data.api.CustomerApi
import com.fieldtrackpro.android.data.model.CustomerDto
import okhttp3.Headers
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.ResponseBody.Companion.toResponseBody
import retrofit2.Response
import java.lang.reflect.Proxy

internal fun cust(
    id: String,
    name: String,
    code: String? = null,
    address: String? = null,
    area: String? = null,
    territory: String? = null
) = CustomerDto(id = id, name = name, outletCode = code, address = address, areaName = area, territoryName = territory)

internal inline fun <reified T> stub(crossinline handler: (String, Array<out Any?>?) -> Any?): T =
    Proxy.newProxyInstance(T::class.java.classLoader, arrayOf(T::class.java)) { _, m, args ->
        when (m.name) {
            "toString" -> "stub"
            "hashCode" -> 1
            "equals" -> false
            else -> handler(m.name, args)
        }
    } as T

internal fun <T> httpError(code: Int): Response<T> = Response.error(code, "{}".toResponseBody("application/json".toMediaTypeOrNull()))

/**
 * Fake GET /customers mirroring the backend contract: no search -> the caller's scope (paged with X-Total-Count);
 * search -> token AND filter over name/code/address, ALPHABETICAL, capped at 50 (what the real server does).
 */
internal class FakeCustomerApi(
    private val scope: List<CustomerDto>,
    private val directory: List<CustomerDto> = scope,
    var failWith: Int? = null
) {
    val calls = mutableListOf<String>()
    val api: CustomerApi = stub { name, args ->
        if (name != "getCustomers") throw IllegalStateException(name)
        val skip = (args!![0] as Int?) ?: 0
        val limit = (args[1] as Int?) ?: 50
        val search = args[2] as String?
        calls += "skip=$skip limit=$limit search=$search"
        failWith?.let { return@stub httpError<List<CustomerDto>>(it) }
        val matches = if (search == null) scope else {
            val tokens = search.lowercase().split(" ").filter { it.isNotBlank() }
            val pool = if (search.trim().length >= 3) directory else scope
            pool.filter { c ->
                val hay = listOfNotNull(c.name, c.outletCode, c.address).joinToString(" ").lowercase()
                tokens.all { hay.contains(it) }
            }.sortedBy { it.name.lowercase() }
        }
        val cap = if (search == null) limit else minOf(limit, 50)
        val page = matches.drop(skip).take(cap)
        Response.success(page, Headers.headersOf("X-Total-Count", matches.size.toString()))
    }
}
