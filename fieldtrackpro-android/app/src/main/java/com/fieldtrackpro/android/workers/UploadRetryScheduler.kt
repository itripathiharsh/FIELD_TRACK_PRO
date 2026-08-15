package com.fieldtrackpro.android.workers

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkRequest
import java.io.File
import java.util.UUID
import java.util.concurrent.TimeUnit

/**
 * P1-6: enqueues the existing MediaUploadWorker/SignatureUploadWorker - with
 * a network constraint and exponential backoff - when a direct (foreground)
 * upload attempt fails transiently. This is the missing wiring the workers
 * were built for but never received (see each worker's own doc comment);
 * it reuses those workers exactly as they already exist rather than
 * introducing a second upload path.
 */
object UploadRetryScheduler {

    private val RETRY_CONSTRAINTS = Constraints.Builder()
        .setRequiredNetworkType(NetworkType.CONNECTED)
        .build()

    /**
     * Persists [fileBytes] to a stable app-private file (a `content://`/picker
     * Uri is not guaranteed re-readable later, e.g. after the picking app's
     * process dies) and enqueues a [MediaUploadWorker] retry.
     *
     * @return true if the retry was successfully scheduled.
     */
    fun queueMediaUpload(
        context: Context,
        visitId: String,
        fileName: String,
        mimeType: String,
        fileBytes: ByteArray,
        isOrder: Boolean = false,
        note: String? = null,
    ): Boolean {
        return try {
            val file = File(context.cacheDir, "pending_upload_${UUID.randomUUID()}")
            file.writeBytes(fileBytes)
            val isDocument = !mimeType.startsWith("image/")
            val inputData = MediaUploadWorker.createInputData(
                visitId = visitId,
                filePath = file.absolutePath,
                fileName = fileName,
                mimeType = mimeType,
                isDocument = isDocument,
                isOrder = isOrder,
                note = note,
            )
            val request = OneTimeWorkRequestBuilder<MediaUploadWorker>()
                .setInputData(inputData)
                .setConstraints(RETRY_CONSTRAINTS)
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, WorkRequest.MIN_BACKOFF_MILLIS, TimeUnit.MILLISECONDS)
                .build()
            WorkManager.getInstance(context).enqueue(request)
            true
        } catch (e: Exception) {
            false
        }
    }

    /**
     * Persists [imageBytes] to a stable app-private file - a signature drawn
     * or a photo picked moments ago must survive even if the app process
     * dies before the network call finishes, the same durability guarantee
     * [queueMediaUpload] already gives photo/document uploads. The raw base64
     * string previously embedded directly in WorkManager `Data` had no such
     * guarantee and is also subject to WorkManager's ~10KB per-request Data
     * size ceiling, which a real signature/photo can exceed.
     *
     * [uniqueWorkName] lets a caller that also attempts a direct (foreground)
     * upload cancel this safety-net job afterwards via
     * `WorkManager.getInstance(context).cancelUniqueWork(uniqueWorkName)` if
     * that direct attempt already succeeded - avoiding a redundant retry
     * while still guaranteeing delivery if the app never gets that far.
     *
     * @return true if the retry was successfully scheduled.
     */
    fun queueSignatureUpload(
        context: Context,
        uniqueWorkName: String,
        visitId: String,
        signatureType: String,
        captureMethod: String,
        imageBytes: ByteArray,
        signatureId: String? = null,
    ): Boolean {
        return try {
            val file = File(context.filesDir, "pending_signature_${UUID.randomUUID()}")
            file.writeBytes(imageBytes)
            val inputData = SignatureUploadWorker.createInputData(
                visitId = visitId,
                signatureType = signatureType,
                captureMethod = captureMethod,
                filePath = file.absolutePath,
                signatureId = signatureId,
            )
            val request = OneTimeWorkRequestBuilder<SignatureUploadWorker>()
                .setInputData(inputData)
                .setConstraints(RETRY_CONSTRAINTS)
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, WorkRequest.MIN_BACKOFF_MILLIS, TimeUnit.MILLISECONDS)
                .build()
            WorkManager.getInstance(context)
                .enqueueUniqueWork(uniqueWorkName, ExistingWorkPolicy.REPLACE, request)
            true
        } catch (e: Exception) {
            false
        }
    }
}
