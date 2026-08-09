package com.fieldtrackpro.android.workers

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.Data
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.data.repository.SignatureRepository

/**
 * Worker for uploading signatures via WorkManager.
 *
 * Phase 6 Section 7: uploads run through WorkManager for resilience.
 */
class SignatureUploadWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    companion object {
        const val KEY_VISIT_ID = "visit_id"
        const val KEY_SIGNATURE_TYPE = "signature_type"
        const val KEY_SIGNATURE_BASE64 = "signature_base64"
        const val KEY_RESULT = "result"

        fun createInputData(
            visitId: String,
            signatureType: String,
            signatureBase64: String
        ): Data = workDataOf(
            KEY_VISIT_ID to visitId,
            KEY_SIGNATURE_TYPE to signatureType,
            KEY_SIGNATURE_BASE64 to signatureBase64
        )
    }

    override suspend fun doWork(): Result {
        val visitId = inputData.getString(KEY_VISIT_ID) ?: return Result.failure()
        val signatureType = inputData.getString(KEY_SIGNATURE_TYPE) ?: return Result.failure()
        val signatureBase64 = inputData.getString(KEY_SIGNATURE_BASE64) ?: return Result.failure()

        return try {
            val tokenManager = TokenManager(applicationContext)
            val repository = SignatureRepository(ApiClient.createSignatureApi(tokenManager))

            when (val result = repository.uploadSignature(visitId, signatureType, signatureBase64)) {
                is Resource.Success -> Result.success(
                    workDataOf(KEY_RESULT to "success")
                )
                is Resource.Error -> {
                    if (shouldRetry(result.message)) {
                        Result.retry()
                    } else {
                        Result.failure(workDataOf(KEY_RESULT to result.message))
                    }
                }
                else -> Result.retry()
            }
        } catch (e: Exception) {
            if (shouldRetry(e.message ?: "")) {
                Result.retry()
            } else {
                Result.failure(workDataOf(KEY_RESULT to e.localizedMessage))
            }
        }
    }

    private fun shouldRetry(errorMessage: String): Boolean {
        val lower = errorMessage.lowercase()
        return !lower.contains("invalid") &&
               !lower.contains("already exists") &&
               !lower.contains("unauthorized") &&
               !lower.contains("forbidden")
    }
}
