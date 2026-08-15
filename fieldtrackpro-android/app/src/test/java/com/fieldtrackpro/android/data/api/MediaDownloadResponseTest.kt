package com.fieldtrackpro.android.data.api

import org.junit.Assert.assertEquals
import org.junit.Test

class MediaDownloadResponseTest {

    @Test
    fun mediaDownloadResponse_fieldsCorrect() {
        val response = MediaDownloadResponse(
            download_url = "https://storage.example.com/media/123?token=abc",
            expires_in_minutes = 15
        )

        assertEquals("https://storage.example.com/media/123?token=abc", response.download_url)
        assertEquals(15, response.expires_in_minutes)
    }
}
