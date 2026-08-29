package com.fieldtrackpro.android.data.api

import com.fieldtrackpro.android.data.model.CustomerDto
import retrofit2.Response
import retrofit2.http.GET
import retrofit2.http.Path
import retrofit2.http.Query

interface CustomerApi {
    @GET("api/v1/customers")
    suspend fun getCustomers(
        @Query("skip") skip: Int? = null,
        @Query("limit") limit: Int? = null,
        @Query("search") search: String? = null,
        @Query("territory_id") territoryId: String? = null,
        @Query("area_id") areaId: String? = null,
    ): Response<List<CustomerDto>>

    @GET("api/v1/customers/{customer_id}")
    suspend fun getCustomerById(
        @Path("customer_id") customerId: String
    ): Response<CustomerDto>
}
