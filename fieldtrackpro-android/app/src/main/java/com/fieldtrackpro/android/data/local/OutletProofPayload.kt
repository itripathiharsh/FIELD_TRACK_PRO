package com.fieldtrackpro.android.data.local

import com.google.gson.annotations.SerializedName

/**
 * One captured outlet proof: the live photo (private file) + the GPS fix taken at the SAME shutter click.
 * Used both as the persisted capture draft and as the offline-queue payload (PendingAction.outletProofPayload).
 * All fields are nullable/defaulted so persisted JSON stays readable across app versions.
 *
 * [idempotencyKey] is generated ONCE at the shutter click, persisted with the draft/queue entry and reused for
 * every retry, so the backend (which dedups on (user, key)) can never store the same capture twice.
 */
data class OutletProofPayload(
    @SerializedName("idempotencyKey") val idempotencyKey: String? = null,
    /** null = NEW outlet (proof is uploaded UNATTACHED, then referenced by the prospect submission). */
    @SerializedName("customerId") val customerId: String? = null,
    @SerializedName("outletName") val outletName: String? = null,
    /** Absolute path of the JPEG in app-private storage (never the gallery). */
    @SerializedName("photoPath") val photoPath: String? = null,
    @SerializedName("latitude") val latitude: Double? = null,
    @SerializedName("longitude") val longitude: Double? = null,
    @SerializedName("accuracyM") val accuracyM: Double? = null,
    /** Device time at the shutter click, ISO-8601 WITH offset (what the server receives). */
    @SerializedName("capturedAt") val capturedAt: String? = null,
    @SerializedName("capturedAtEpochMs") val capturedAtEpochMs: Long? = null,
    @SerializedName("isMock") val isMock: Boolean = false,
    @SerializedName("deviceInfo") val deviceInfo: String? = null,
    /** Set once the server stored the proof (new-outlet drafts keep it until the prospect is submitted). */
    @SerializedName("serverProofId") val serverProofId: String? = null,
    @SerializedName("uploadedAtEpochMs") val uploadedAtEpochMs: Long? = null
)
