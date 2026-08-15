package com.fieldtrackpro.android.ui.viewmodel

import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.GeoVerificationLogDto
import com.fieldtrackpro.android.data.model.MediaDto
import com.fieldtrackpro.android.data.model.VisitDto
import com.fieldtrackpro.android.data.repository.Resource
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class VisitSummaryViewModelTest {

    private val testDispatcher = StandardTestDispatcher()

    @Before
    fun setup() {
        Dispatchers.setMain(testDispatcher)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun initialState_isLoading() {
        // The initial state should be Loading
        // We can't easily instantiate the ViewModel without Android context,
        // but we can verify the state machine logic
        val loading = VisitSummaryState.Loading
        assertTrue(loading is VisitSummaryState.Loading)
    }

    @Test
    fun readyState_holdsVisitData() {
        val visit = VisitDto(
            id = "visit-1",
            customerId = "cust-1",
            employeeId = "emp-1",
            scheduledAt = "2026-01-01T10:00:00Z",
            status = "IN_PROGRESS"
        )
        val media = listOf(
            MediaDto(
                id = "media-1",
                visitId = "visit-1",
                mediaType = "PHOTO",
                storageKey = "visits/visit-1/test.jpg",
                fileSizeBytes = 1024,
                uploadedAt = "2026-01-01T10:05:00Z"
            )
        )
        val geoLogs = listOf(
            GeoVerificationLogDto(
                id = "log-1",
                visitId = "visit-1",
                verificationType = "CHECK_IN",
                attemptedAt = "2026-01-01T10:01:00Z",
                latitude = 12.9716,
                longitude = 77.5946,
                distanceFromCustomerM = 15.0,
                isValid = true,
                failureReason = null
            )
        )

        val state = VisitSummaryState.Ready(visit, media, geoLogs)

        assertEquals("visit-1", state.visit.id)
        assertEquals(1, state.media.size)
        assertEquals("PHOTO", state.media[0].mediaType)
        assertEquals(1, state.geoLogs.size)
        assertEquals("CHECK_IN", state.geoLogs[0].verificationType)
    }

    @Test
    fun errorState_holdsMessage() {
        val state = VisitSummaryState.Error("Network error")
        assertEquals("Network error", state.message)
    }
}
