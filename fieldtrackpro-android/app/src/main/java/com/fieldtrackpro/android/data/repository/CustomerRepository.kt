package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.CustomerApi
import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.data.model.CustomerPage

/**
 * Repository for Customer operations with server-side pagination, search, and total-count preservation.
 *
 * APP-CUST-002: Parses X-Total-Count header and encapsulates within CustomerPage.
 */
class CustomerRepository(private val customerApi: CustomerApi) {

    /**
     * Fetch paginated customers with server-side search, filtering, and total count metadata.
     */
    suspend fun getCustomers(
        skip: Int = 0,
        limit: Int = 50,
        search: String? = null,
        territoryId: String? = null,
        areaId: String? = null,
    ): Resource<CustomerPage> {
        return try {
            val response = customerApi.getCustomers(
                skip = skip,
                limit = limit,
                search = search,
                territoryId = territoryId,
                areaId = areaId
            )
            if (response.isSuccessful && response.body() != null) {
                val customers = response.body()!!
                val totalCountHeader = response.headers().get("X-Total-Count")
                val totalCount = totalCountHeader?.toIntOrNull() ?: customers.size
                Resource.Success(
                    CustomerPage(
                        customers = customers,
                        totalCount = totalCount,
                        skip = skip,
                        limit = limit
                    )
                )
            } else {
                Resource.Error("Failed to fetch customers (${response.code()})", response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    /**
     * Direct single customer lookup by ID.
     */
    suspend fun getCustomerById(customerId: String): Resource<CustomerDto> {
        return try {
            val response = customerApi.getCustomerById(customerId)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Customer not found (${response.code()})", response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }
}
