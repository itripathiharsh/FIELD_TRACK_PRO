package com.fieldtrackpro.android.data.api

import com.fieldtrackpro.android.data.model.MediaDto
import okhttp3.MultipartBody
import retrofit2.Response
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query

interface MediaApi {
    @Multipart
    @POST("api/v1/visits/{visit_id}/media")
    suspend fun uploadVisitMedia(
        @Path("visit_id") visitId: String,
        @Part file: MultipartBody.Part,
        // P2-B: order capture reuses this same upload endpoint with
        // is_order=true + a diary note, exactly like the web client.
        @Query("is_order") isOrder: Boolean = false,
        @Query("note") note: String? = null
    ): Response<MediaDto>

    @GET("api/v1/visits/{visit_id}/media")
    suspend fun getVisitMediaList(
        @Path("visit_id") visitId: String
    ): Response<List<MediaDto>>

    @GET("api/v1/media/{media_id}")
    suspend fun getMediaMetadata(
        @Path("media_id") mediaId: String
    ): Response<MediaDto>

    @GET("api/v1/media/{media_id}/download")
    suspend fun getMediaDownloadUrl(
        @Path("media_id") mediaId: String,
        @Query("expiry_minutes") expiryMinutes: Int = 15
    ): Response<MediaDownloadResponse>
}

data class MediaDownloadResponse(
    val download_url: String,
    val expires_in_minutes: Int
)
