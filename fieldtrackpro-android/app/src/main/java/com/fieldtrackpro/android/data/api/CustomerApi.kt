package com.fieldtrackpro.android.data.api

import com.fieldtrackpro.android.data.model.BrandDto
import com.fieldtrackpro.android.data.model.BrandCreate
import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.data.model.CustomerProspectCreate
import com.fieldtrackpro.android.data.model.CustomerRequirementCreate
import com.fieldtrackpro.android.data.model.CustomerRequirementDto
import com.fieldtrackpro.android.data.model.LocationProposalCreate
import com.fieldtrackpro.android.data.model.LocationProposalDto
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
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

    @POST("api/v1/customers/{customer_id}/location-proposals")
    suspend fun proposeCustomerLocation(
        @Path("customer_id") customerId: String,
        @Body proposal: LocationProposalCreate
    ): Response<LocationProposalDto>

    @GET("api/v1/customers/{customer_id}/location-proposals")
    suspend fun getCustomerLocationProposals(
        @Path("customer_id") customerId: String
    ): Response<List<LocationProposalDto>>

    @POST("api/v1/customers/prospect")
    suspend fun createCustomerProspect(
        @Body prospect: CustomerProspectCreate
    ): Response<CustomerDto>

    @GET("api/v1/customers/{customer_id}/requirements")
    suspend fun getCustomerRequirements(
        @Path("customer_id") customerId: String
    ): Response<List<CustomerRequirementDto>>

    @POST("api/v1/customers/{customer_id}/requirements")
    suspend fun createCustomerRequirement(
        @Path("customer_id") customerId: String,
        @Body req: CustomerRequirementCreate
    ): Response<CustomerRequirementDto>

    @GET("api/v1/brands")
    suspend fun getBrands(
        @Query("active_only") activeOnly: Boolean = true
    ): Response<List<BrandDto>>

    @POST("api/v1/brands")
    suspend fun createBrand(
        @Body request: BrandCreate
    ): Response<BrandDto>
}

