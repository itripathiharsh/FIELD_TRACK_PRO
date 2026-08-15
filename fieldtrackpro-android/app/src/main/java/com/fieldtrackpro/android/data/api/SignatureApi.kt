package com.fieldtrackpro.android.data.api

import com.fieldtrackpro.android.data.model.SignatureCreateRequest
import com.fieldtrackpro.android.data.model.SignatureDto
import com.fieldtrackpro.android.data.model.SignatureReplaceRequest
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path

interface SignatureApi {
    @POST("api/v1/visits/{visit_id}/signatures")
    suspend fun uploadSignature(
        @Path("visit_id") visitId: String,
        @Body payload: SignatureCreateRequest
    ): Response<SignatureDto>

    @POST("api/v1/visits/{visit_id}/signatures/{signature_id}/replace")
    suspend fun replaceSignature(
        @Path("visit_id") visitId: String,
        @Path("signature_id") signatureId: String,
        @Body payload: SignatureReplaceRequest
    ): Response<SignatureDto>

    @GET("api/v1/visits/{visit_id}/signatures")
    suspend fun getVisitSignatures(
        @Path("visit_id") visitId: String
    ): Response<List<SignatureDto>>
}
