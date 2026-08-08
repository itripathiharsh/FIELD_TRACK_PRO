package com.fieldtrackpro.android.data.api

import com.fieldtrackpro.android.data.model.MediaDto
import okhttp3.MultipartBody
import retrofit2.Response
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path

interface MediaApi {
    @Multipart
    @POST("api/v1/visits/{visit_id}/media")
    suspend fun uploadVisitMedia(
        @Path("visit_id") visitId: String,
        @Part file: MultipartBody.Part
    ): Response<MediaDto>

    @GET("api/v1/visits/{visit_id}/media")
    suspend fun getVisitMediaList(
        @Path("visit_id") visitId: String
    ): Response<List<MediaDto>>

    @GET("api/v1/media/{media_id}")
    suspend fun getMediaMetadata(
        @Path("media_id") mediaId: String
    ): Response<MediaDto>
}
