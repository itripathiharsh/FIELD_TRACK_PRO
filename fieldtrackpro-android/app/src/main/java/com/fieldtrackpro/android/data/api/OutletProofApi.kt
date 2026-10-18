package com.fieldtrackpro.android.data.api

import com.fieldtrackpro.android.data.model.OutletProofRead
import okhttp3.MultipartBody
import okhttp3.ResponseBody
import retrofit2.Response
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path

interface OutletProofApi {
    /**
     * Uploads ONE outlet proof (live photo + the GPS fix taken at the same shutter click).
     * [parts] is built by OutletProofMultipart so the field names live in one place.
     */
    @Multipart
    @POST("api/v1/customers/outlet-proofs")
    suspend fun uploadOutletProof(@Part parts: List<MultipartBody.Part>): Response<OutletProofRead>

    /** The outlet's approved primary photo (image/jpeg bytes); 404 when there is none. */
    @GET("api/v1/customers/{customer_id}/outlet-image")
    suspend fun getOutletImage(@Path("customer_id") customerId: String): Response<ResponseBody>
}
