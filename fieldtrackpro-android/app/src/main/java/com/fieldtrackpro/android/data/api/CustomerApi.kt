package com.fieldtrackpro.android.data.api

import com.fieldtrackpro.android.data.model.CustomerDto
import retrofit2.Response
import retrofit2.http.GET
import retrofit2.http.Path

interface CustomerApi {
    @GET("api/v1/customers")
    suspend fun getCustomers(): Response<List<CustomerDto>>

    @GET("api/v1/customers/{customer_id}")
    suspend fun getCustomerById(
        @Path("customer_id") customerId: String
    ): Response<CustomerDto>
}
