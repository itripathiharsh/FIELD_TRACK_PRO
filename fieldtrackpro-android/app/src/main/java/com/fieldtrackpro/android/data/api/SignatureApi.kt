package com.fieldtrackpro.android.data.api

import com.fieldtrackpro.android.data.model.SignatureDto
import okhttp3.MultipartBody
import okhttp3.RequestBody
import retrofit2.Response
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path

interface SignatureApi {
    @Multipart
    @POST("api/v1/visits/{visit_id}/signatures")
    suspend fun uploadSignature(
        @Path("visit_id") visitId: String,
        @Part signatureType: MultipartBody.Part,
        @Part signatureImage: MultipartBody.Part
    ): Response<SignatureDto>

    @GET("api/v1/visits/{visit_id}/signatures")
    suspend fun getVisitSignatures(
        @Path("visit_id") visitId: String
    ): Response<List<SignatureDto>>
}
