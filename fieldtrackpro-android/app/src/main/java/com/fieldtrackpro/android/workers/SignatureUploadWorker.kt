package com.fieldtrackpro.android.workers

import android.content.Context
import android.util.Base64
import androidx.work.CoroutineWorker
import androidx.work.Data
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.data.repository.SignatureRepository

/**
 * Worker for uploading signatures/acknowledgements via WorkManager.
 *
 * Reads the image from a durable file (see UploadRetryScheduler.queueSignatureUpload)
 * rather than holding it in WorkManager `Data` - a raw base64 signature/photo
 * string embedded directly in `Data` had no durability guarantee beyond the
 * WorkManager database itself and could exceed Data's ~10KB size ceiling.
 */
class SignatureUploadWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    companion object {
        const val KEY_VISIT_ID = "visit_id"
        const val KEY_SIGNATURE_TYPE = "signature_type"
        const val KEY_CAPTURE_METHOD = "capture_method"
        const val KEY_FILE_PATH = "file_path"
        // Present only when this attempt is replacing an existing (not yet
        // superseded) signature rather than creating a fresh one.
        const val KEY_SIGNATURE_ID = "signature_id"
        const val KEY_RESULT = "result"

        fun createInputData(
            visitId: String,
            signatureType: String,
            captureMethod: String,
            filePath: String,
            signatureId: String? = null,
        ): Data = workDataOf(
            KEY_VISIT_ID to visitId,
            KEY_SIGNATURE_TYPE to signatureType,
            KEY_CAPTURE_METHOD to captureMethod,
            KEY_FILE_PATH to filePath,
            KEY_SIGNATURE_ID to signatureId,
        )
    }

    override suspend fun doWork(): Result {
        val visitId = inputData.getString(KEY_VISIT_ID) ?: return Result.failure()
        val signatureType = inputData.getString(KEY_SIGNATURE_TYPE) ?: return Result.failure()
        val captureMethod = inputData.getString(KEY_CAPTURE_METHOD) ?: "SIGNATURE"
        val filePath = inputData.getString(KEY_FILE_PATH) ?: return Result.failure()
        val signatureId = inputData.getString(KEY_SIGNATURE_ID)

        val file = java.io.File(filePath)
        if (!file.exists()) {
            // Nothing left to retry (already delivered and cleaned up, or
            // the file was never written) - treat as done, not a failure.
            return Result.success()
        }

        return try {
            val imageBytes = file.readBytes()
            val base64 = Base64.encodeToString(imageBytes, Base64.NO_WRAP)

            val tokenManager = TokenManager(applicationContext)
            val repository = SignatureRepository(ApiClient.createSignatureApi(tokenManager))

            val result = if (signatureId != null) {
                repository.replaceSignature(visitId, signatureId, base64, captureMethod)
            } else {
                repository.uploadSignature(visitId, signatureType, base64, captureMethod)
            }

            when (result) {
                is Resource.Success -> {
                    file.delete()
                    Result.success(workDataOf(KEY_RESULT to "success"))
                }
                is Resource.Error -> {
                    // SIGNATURE_ALREADY_EXISTS means a direct (foreground)
                    // attempt already delivered this same capture while this
                    // safety-net job was still waiting on its network
                    // constraint - not a real failure, just redundant.
                    if (UploadRetryPolicy.isTransientFailure(result.message)) {
                        Result.retry()
                    } else {
                        file.delete()
                        Result.failure(workDataOf(KEY_RESULT to result.message))
                    }
                }
                else -> Result.retry()
            }
        } catch (e: Exception) {
            if (UploadRetryPolicy.isTransientFailure(e.message ?: "")) {
                Result.retry()
            } else {
                file.delete()
                Result.failure(workDataOf(KEY_RESULT to e.localizedMessage))
            }
        }
    }
}
