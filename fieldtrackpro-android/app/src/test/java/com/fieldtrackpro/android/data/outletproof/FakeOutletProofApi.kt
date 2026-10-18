package com.fieldtrackpro.android.data.outletproof

import com.fieldtrackpro.android.data.api.OutletProofApi
import com.fieldtrackpro.android.data.model.OutletProofRead
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.ResponseBody
import okhttp3.ResponseBody.Companion.toResponseBody
import okio.Buffer
import retrofit2.Response
import java.io.IOException

/** Decoded multipart request: field name -> text value ("photo" -> "<file:filename:size>"). */
data class RecordedUpload(val fields: Map<String, String>, val photoBytes: ByteArray?)

/**
 * Scriptable in-memory backend mimicking POST /customers/outlet-proofs idempotency: a repeated
 * (idempotency_key) returns the SAME stored proof with 201.
 */
class FakeOutletProofApi : OutletProofApi {
    var behavior: () -> Response<OutletProofRead>? = { null } // null => default (dedup store)
    var throwsOnUpload: IOException? = null

    val uploads = mutableListOf<RecordedUpload>()
    val stored = mutableMapOf<String, OutletProofRead>() // key = idempotency_key

    fun err(code: Int, body: String = "{}") =
        Response.error<OutletProofRead>(code, body.toResponseBody("application/json".toMediaTypeOrNull()))

    fun errCode(code: Int, errorCode: String, message: String = "server says no") =
        err(code, """{"error":{"code":"$errorCode","message":"$message","details":null,"request_id":"r1"}}""")

    override suspend fun uploadOutletProof(parts: List<MultipartBody.Part>): Response<OutletProofRead> {
        val rec = decode(parts)
        uploads += rec
        throwsOnUpload?.let { throw it }
        behavior()?.let { return it }
        val key = rec.fields["idempotency_key"] ?: "none"
        val proof = stored.getOrPut(key) {
            val attached = rec.fields.containsKey("customer_id")
            OutletProofRead(
                id = "proof-${stored.size + 1}",
                customerId = rec.fields["customer_id"],
                kind = "INITIAL",
                status = if (attached) "PENDING" else "UNATTACHED",
                latitude = rec.fields["latitude"]?.toDouble(),
                longitude = rec.fields["longitude"]?.toDouble()
            )
        }
        return Response.success(201, proof)
    }

    override suspend fun getOutletImage(customerId: String): Response<ResponseBody> = throw UnsupportedOperationException()

    companion object {
        fun decode(parts: List<MultipartBody.Part>): RecordedUpload {
            val fields = linkedMapOf<String, String>()
            var photo: ByteArray? = null
            for (p in parts) {
                val disp = p.headers?.get("Content-Disposition").orEmpty()
                val name = Regex("name=\"([^\"]*)\"").find(disp)?.groupValues?.get(1) ?: continue
                val buf = Buffer().also { p.body.writeTo(it) }
                if (disp.contains("filename=")) {
                    val bytes = buf.readByteArray()
                    photo = bytes
                    fields[name] = "<file:" + Regex("filename=\"([^\"]*)\"").find(disp)?.groupValues?.get(1) + ":" + bytes.size + ">"
                } else {
                    fields[name] = buf.readUtf8()
                }
            }
            return RecordedUpload(fields, photo)
        }
    }
}
