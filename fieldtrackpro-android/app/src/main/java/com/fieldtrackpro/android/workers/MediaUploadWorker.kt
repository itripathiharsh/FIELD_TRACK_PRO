package com.fieldtrackpro.android.workers

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.Data
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.MediaRepository
import com.fieldtrackpro.android.data.repository.Resource
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody

/**
 * Worker for uploading media files (photos/documents) via WorkManager.

 * Phase 6 Section 7: "On poor field networks, uploads run through WorkManager
 * (not a direct fire-and-forget coroutine) so a photo upload that fails
 * mid-transfer retries automatically with backoff"
 */
class MediaUploadWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    companion object {
        const val KEY_VISIT_ID = "visit_id"
        const val KEY_FILE_PATH = "file_path"
        const val KEY_FILE_NAME = "file_name"
        const val KEY_MIME_TYPE = "mime_type"
        const val KEY_IS_DOCUMENT = "is_document"
        // P1-6: order capture (P2-B) reuses this same worker/upload pipeline
        // with is_order=true - it must retry through the order-capture
        // endpoint, not the plain visit-media one, or the note gets dropped.
        const val KEY_IS_ORDER = "is_order"
        const val KEY_NOTE = "note"
        const val KEY_RESULT = "result"

        fun createInputData(
            visitId: String,
            filePath: String,
            fileName: String,
            mimeType: String,
            isDocument: Boolean,
            isOrder: Boolean = false,
            note: String? = null,
        ): Data = workDataOf(
            KEY_VISIT_ID to visitId,
            KEY_FILE_PATH to filePath,
            KEY_FILE_NAME to fileName,
            KEY_MIME_TYPE to mimeType,
            KEY_IS_DOCUMENT to isDocument,
            KEY_IS_ORDER to isOrder,
            KEY_NOTE to note,
        )
    }

    override suspend fun doWork(): Result {
        val visitId = inputData.getString(KEY_VISIT_ID) ?: return Result.failure()
        val filePath = inputData.getString(KEY_FILE_PATH) ?: return Result.failure()
        val fileName = inputData.getString(KEY_FILE_NAME) ?: return Result.failure()
        val mimeType = inputData.getString(KEY_MIME_TYPE) ?: return Result.failure()
        val isOrder = inputData.getBoolean(KEY_IS_ORDER, false)
        val note = inputData.getString(KEY_NOTE)

        val file = java.io.File(filePath)
        return try {
            val fileBytes = file.readBytes()

            val tokenManager = TokenManager(applicationContext)
            val repository = MediaRepository(ApiClient.createMediaApi(tokenManager))

            val result = if (isOrder) {
                repository.uploadOrderCapture(visitId, fileName, mimeType, fileBytes, note)
            } else {
                repository.uploadVisitMedia(visitId, fileName, mimeType, fileBytes)
            }
            when (result) {
                is Resource.Success -> {
                    file.delete()
                    Result.success(workDataOf(KEY_RESULT to "success"))
                }
                is Resource.Error -> {
                    // Retry on transient errors, fail on permanent errors
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
