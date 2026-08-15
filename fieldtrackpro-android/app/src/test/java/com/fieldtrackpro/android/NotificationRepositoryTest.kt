package com.fieldtrackpro.android

import com.fieldtrackpro.android.data.api.NotificationApi
import com.fieldtrackpro.android.data.model.NotificationDto
import com.fieldtrackpro.android.data.repository.NotificationRepository
import com.fieldtrackpro.android.data.repository.Resource
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.Response

@OptIn(ExperimentalCoroutinesApi::class)
class NotificationRepositoryTest {

    private val fakeApi = object : NotificationApi {
        override suspend fun getMyNotifications(): Response<List<NotificationDto>> {
            val notifications = listOf(
                NotificationDto("1", "u1", "v1", "NEW_VISIT", "New visit", false, "2026-01-01T10:00:00Z"),
                NotificationDto("2", "u1", null, "REMINDER", "Reminder", true, "2026-01-01T09:00:00Z")
            )
            return Response.success(notifications)
        }

        override suspend fun markAsRead(notificationId: String): Response<Map<String, String>> {
            return Response.success(mapOf("status" to "ok"))
        }
    }

    private val repository = NotificationRepository(fakeApi)

    @Test
    fun getMyNotifications_returnsSuccess() = runTest {
        val result = repository.getMyNotifications()

        assertTrue("Result should be Success", result is Resource.Success)
        val data = (result as Resource.Success).data
        assertEquals(2, data.size)
        assertEquals("New visit", data[0].message)
        assertEquals("Reminder", data[1].message)
    }

    @Test
    fun markAsRead_returnsSuccess() = runTest {
        val result = repository.markAsRead("1")

        assertTrue("Result should be Success", result is Resource.Success)
    }

    @Test
    fun getMyNotifications_emptyList_returnsSuccess() = runTest {
        val emptyApi = object : NotificationApi {
            override suspend fun getMyNotifications(): Response<List<NotificationDto>> {
                return Response.success(emptyList())
            }
            override suspend fun markAsRead(notificationId: String): Response<Map<String, String>> {
                return Response.success(mapOf("status" to "ok"))
            }
        }
        val emptyRepo = NotificationRepository(emptyApi)
        val result = emptyRepo.getMyNotifications()

        assertTrue("Result should be Success", result is Resource.Success)
        assertTrue((result as Resource.Success).data.isEmpty())
    }

    @Test
    fun getMyNotifications_apiError_returnsError() = runTest {
        val errorApi = object : NotificationApi {
            override suspend fun getMyNotifications(): Response<List<NotificationDto>> {
                return Response.error(500, okhttp3.ResponseBody.create(null, "Server error"))
            }
            override suspend fun markAsRead(notificationId: String): Response<Map<String, String>> {
                return Response.success(mapOf("status" to "ok"))
            }
        }
        val errorRepo = NotificationRepository(errorApi)
        val result = errorRepo.getMyNotifications()

        assertTrue("Result should be Error", result is Resource.Error)
    }
}
