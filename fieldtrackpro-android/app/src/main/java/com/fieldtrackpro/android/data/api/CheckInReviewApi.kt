package com.fieldtrackpro.android.data.api

import com.google.gson.annotations.SerializedName
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.POST

/** Employee side of the admin check-in verification (the admin queue itself is served to admins by the backend). */
interface CheckInReviewApi {
    @POST("api/v1/checkin-reviews/request")
    suspend fun requestVerification(@Body body: VerificationRequestBody): Response<CheckInReviewDto>
}

data class VerificationRequestBody(
    @SerializedName("visit_id") val visitId: String,
    val latitude: Double,
    val longitude: Double,
    @SerializedName("accuracy_m") val accuracyM: Double,
    @SerializedName("is_mock_location") val isMockLocation: Boolean = false,
    /** When the device took this fix, ISO-8601 UTC. */
    @SerializedName("captured_at") val capturedAt: String,
    val note: String? = null
)

data class CheckInReviewDto(
    val id: String,
    val kind: String,
    val status: String
)
