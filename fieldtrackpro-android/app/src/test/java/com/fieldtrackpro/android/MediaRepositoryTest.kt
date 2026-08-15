package com.fieldtrackpro.android

import com.fieldtrackpro.android.data.api.MediaApi
import com.fieldtrackpro.android.data.api.MediaDownloadResponse
import com.fieldtrackpro.android.data.model.MediaDto
import com.fieldtrackpro.android.data.repository.MediaRepository
import com.fieldtrackpro.android.data.repository.Resource
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import okhttp3.MultipartBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.Response

/**
 * P2-B: order capture reuses the media upload pipeline with is_order=true -
 * these tests confirm the repository forwards that flag and the note
 * correctly, and that a plain attachment upload still defaults is_order to
 * false (the P0/P1 behavior must not change).
 */
@OptIn(ExperimentalCoroutinesApi::class)
class MediaRepositoryTest {

    private fun mediaDto(mediaType: String, note: String? = null) = MediaDto(
        id = "media-1",
        visitId = "visit-1",
        mediaType = mediaType,
        storageKey = "visits/visit-1/media-1.jpg",
        fileSizeBytes = 1024,
        note = note,
        uploadedAt = "2026-01-01T10:00:00Z"
    )

    private class RecordingMediaApi(private val response: Response<MediaDto>) : MediaApi {
        var lastIsOrder: Boolean? = null
        var lastNote: String? = null

        override suspend fun uploadVisitMedia(
            visitId: String,
            file: MultipartBody.Part,
            isOrder: Boolean,
            note: String?
        ): Response<MediaDto> {
            lastIsOrder = isOrder
            lastNote = note
            return response
        }

        override suspend fun getVisitMediaList(visitId: String): Response<List<MediaDto>> =
            Response.success(emptyList())

        override suspend fun getMediaMetadata(mediaId: String): Response<MediaDto> = response

        override suspend fun getMediaDownloadUrl(mediaId: String, expiryMinutes: Int): Response<MediaDownloadResponse> =
            Response.success(MediaDownloadResponse("https://example.test/x", 15))
    }

    @Test
    fun uploadOrderCapture_sendsIsOrderTrueAndNote() = runTest {
        val api = RecordingMediaApi(Response.success(mediaDto("ORDER", "5x Usha fans")))
        val repo = MediaRepository(api)

        val result = repo.uploadOrderCapture("visit-1", "order.jpg", "image/jpeg", byteArrayOf(1, 2, 3), "5x Usha fans")

        assertTrue("Result should be Success", result is Resource.Success)
        assertEquals(true, api.lastIsOrder)
        assertEquals("5x Usha fans", api.lastNote)
        val media = (result as Resource.Success).data
        assertEquals("ORDER", media.mediaType)
        assertEquals("5x Usha fans", media.note)
        assertTrue("An order capture must preview like a photo", media.isPhoto)
        assertTrue(media.isOrder)
    }

    @Test
    fun uploadVisitMedia_plainAttachment_defaultsIsOrderFalse() = runTest {
        val api = RecordingMediaApi(Response.success(mediaDto("PHOTO")))
        val repo = MediaRepository(api)

        val result = repo.uploadVisitMedia("visit-1", "site.jpg", "image/jpeg", byteArrayOf(1, 2, 3))

        assertTrue("Result should be Success", result is Resource.Success)
        assertEquals(false, api.lastIsOrder)
        assertEquals(null, api.lastNote)
        assertFalse((result as Resource.Success).data.isOrder)
    }

    @Test
    fun uploadOrderCapture_apiError_returnsError() = runTest {
        val api = RecordingMediaApi(Response.error(400, okhttp3.ResponseBody.create(null, "rejected")))
        val repo = MediaRepository(api)

        val result = repo.uploadOrderCapture("visit-1", "order.jpg", "image/jpeg", byteArrayOf(1), "note")

        assertTrue("Result should be Error", result is Resource.Error)
    }

    @Test
    fun uploadOrderCapture_withoutNote_sendsNullNote() = runTest {
        val api = RecordingMediaApi(Response.success(mediaDto("ORDER")))
        val repo = MediaRepository(api)

        repo.uploadOrderCapture("visit-1", "order.jpg", "image/jpeg", byteArrayOf(1), null)

        assertEquals(null, api.lastNote)
    }
}
