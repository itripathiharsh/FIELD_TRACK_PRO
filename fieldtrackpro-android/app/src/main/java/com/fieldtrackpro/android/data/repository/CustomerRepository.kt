package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.CustomerApi
import com.fieldtrackpro.android.data.model.CustomerDto

class CustomerRepository(private val customerApi: CustomerApi) {
    suspend fun getCustomers(): Resource<List<CustomerDto>> {
        return try {
            val response = customerApi.getCustomers()
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Failed to fetch customers (${response.code()})")
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }

    suspend fun getCustomerById(customerId: String): Resource<CustomerDto> {
        return try {
            val response = customerApi.getCustomerById(customerId)
            if (response.isSuccessful && response.body() != null) {
                Resource.Success(response.body()!!)
            } else {
                Resource.Error("Customer not found (${response.code()})")
            }
        } catch (e: Exception) {
            Resource.Error("Network error: ${e.localizedMessage}")
        }
    }
}
