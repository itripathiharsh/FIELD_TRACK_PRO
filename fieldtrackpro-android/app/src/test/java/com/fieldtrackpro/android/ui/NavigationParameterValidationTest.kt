package com.fieldtrackpro.android.ui

import com.fieldtrackpro.android.ui.navigation.Screen
import com.fieldtrackpro.android.utils.SessionManager
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.net.URLDecoder

class NavigationParameterValidationTest {

    @Test
    fun testAttachmentPreview_routeEncodingAndDecoding() {
        val originalFileName = "Site Photo #1 & Invoice.png"
        val route = Screen.AttachmentPreview.createRoute("media-123", originalFileName, true)

        // Route should contain encoded characters instead of raw spaces or '#'
        org.junit.Assert.assertTrue(route.contains("media-123"))
        org.junit.Assert.assertFalse(route.contains(" #1 "))

        val rawEncodedPart = route.substringAfter("media-123/").substringBefore("/true")
        val decoded = URLDecoder.decode(rawEncodedPart, "UTF-8")
        assertEquals(originalFileName, decoded)
    }

    @Test
    fun testPendingDeepLink_flow() {
        SessionManager.reset()
        assertNull(SessionManager.getPendingDeepLink())

        SessionManager.setPendingDeepLink("vis-999")
        assertEquals("vis-999", SessionManager.getPendingDeepLink())

        val consumed = SessionManager.consumePendingDeepLink()
        assertEquals("vis-999", consumed)
        assertNull(SessionManager.getPendingDeepLink())
    }
}
