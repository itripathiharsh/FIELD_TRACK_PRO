package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.CustomerApi
import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.data.model.CustomerPage
import com.fieldtrackpro.android.data.model.CustomerProspectCreate
import com.fieldtrackpro.android.data.model.CustomerRequirementCreate
import com.fieldtrackpro.android.data.model.CustomerRequirementDto
import com.fieldtrackpro.android.data.model.LocationProposalCreate
import com.fieldtrackpro.android.data.model.LocationProposalDto
import org.json.JSONObject

/**
 * Repository for Customer operations with server-side pagination, search, location proposals, and prospect creation.
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

    /**
     * Submit a GPS location proposal for an existing customer.
     * Note: Does NOT directly overwrite official coordinates. Awaiting Admin approval.
     */
    suspend fun proposeCustomerLocation(
        customerId: String,
        proposal: LocationProposalCreate
    ): Resource<LocationProposalDto> {
        return try {
            val response = customerApi.proposeCustomerLocation(customerId, proposal)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                val errorBody = response.errorBody()?.string()
                val message = parseErrorMessage(errorBody) ?: "Failed to submit location proposal (${response.code()})"
                Resource.Error(message, response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    /**
     * Fetch location proposals history for a customer.
     */
    suspend fun getCustomerLocationProposals(customerId: String): Resource<List<LocationProposalDto>> {
        return try {
            val response = customerApi.getCustomerLocationProposals(customerId)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Failed to fetch location proposals (${response.code()})", response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    /**
     * Register a new Customer / Outlet prospect from the field.
     */
    suspend fun createCustomerProspect(prospect: CustomerProspectCreate): Resource<CustomerDto> {
        return try {
            val response = customerApi.createCustomerProspect(prospect)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                val errorBody = response.errorBody()?.string()
                val message = parseErrorMessage(errorBody) ?: "Failed to create customer (${response.code()})"
                Resource.Error(message, response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    /**
     * Fetch requirements for a customer.
     */
    suspend fun getCustomerRequirements(customerId: String): Resource<List<CustomerRequirementDto>> {
        return try {
            val response = customerApi.getCustomerRequirements(customerId)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Failed to fetch requirements (${response.code()})", response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    /**
     * Create a requirement for a customer.
     */
    suspend fun createCustomerRequirement(
        customerId: String,
        req: CustomerRequirementCreate
    ): Resource<CustomerRequirementDto> {
        return try {
            val response = customerApi.createCustomerRequirement(customerId, req)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Failed to create requirement (${response.code()})", response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    /**
     * Get master brand list.
     */
    suspend fun getBrands(activeOnly: Boolean = true): Resource<List<com.fieldtrackpro.android.data.model.BrandDto>> {
        return try {
            val response = customerApi.getBrands(activeOnly)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Failed to fetch brands (${response.code()})", response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    suspend fun getBrandNames(activeOnly: Boolean = true): Resource<List<String>> {
        return when (val res = getBrands(activeOnly)) {
            is Resource.Success -> Resource.Success(res.data.map { it.name })
            is Resource.Error -> Resource.Error(res.message ?: "Failed to fetch brands", res.code)
            is Resource.Loading -> Resource.Loading()
        }
    }

    /**
     * Create/register a new brand dynamically.
     */
    suspend fun createBrand(name: String): Resource<com.fieldtrackpro.android.data.model.BrandDto> {
        return try {
            val response = customerApi.createBrand(com.fieldtrackpro.android.data.model.BrandCreate(name = name))
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                val errorBody = response.errorBody()?.string()
                val message = parseErrorMessage(errorBody) ?: "Failed to create brand (${response.code()})"
                Resource.Error(message, response.code())
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    private fun parseErrorMessage(errorJson: String?): String? {
        if (errorJson.isNullOrBlank()) return null
        return try {
            val obj = JSONObject(errorJson)
            if (obj.has("error")) {
                val errorObj = obj.getJSONObject("error")
                if (errorObj.has("message")) errorObj.getString("message") else null
            } else if (obj.has("detail")) {
                obj.getString("detail")
            } else {
                null
            }
        } catch (_: Exception) {
            null
        }
    }
}
