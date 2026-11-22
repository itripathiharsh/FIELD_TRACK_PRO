package com.fieldtrackpro.android.premiumui

import com.fieldtrackpro.android.data.api.WorkdayApi
import com.fieldtrackpro.android.data.local.InMemorySharedPreferences
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.data.repository.WorkdayRepository
import kotlinx.coroutines.runBlocking
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.Response
import java.lang.reflect.Proxy

/** Start/End Day must never send or queue (0,0). */
class WorkdayRepositoryGpsGuardTest {
    private val calls = mutableListOf<String>()

    private val api = Proxy.newProxyInstance(WorkdayApi::class.java.classLoader, arrayOf(WorkdayApi::class.java)) { _, m, _ ->
        when (m.name) {
            "toString" -> "stub"
            "hashCode" -> 1
            "equals" -> false
            else -> {
                calls += m.name
                Response.error<Any>(409, "{}".toResponseBody("application/json".toMediaTypeOrNull()))
            }
        }
    } as WorkdayApi

    private val queue = OfflineQueueManager(InMemorySharedPreferences())
    private val tokens = TokenManager(null, InMemorySharedPreferences())
    private val repo = WorkdayRepository(api, queue, tokens)

    @Test fun endDayWithNullIslandIsRefusedWithoutNetworkOrQueue() = runBlocking {
        val res = repo.endDay(0.0, 0.0, accuracyM = null, notes = "x")
        assertTrue(res is Resource.Error)
        assertTrue(calls.isEmpty())
        assertTrue(queue.getQueue().isEmpty())
    }

    @Test fun startDayWithNullIslandIsRefusedEvenInOfflineMode() = runBlocking {
        val res = repo.startDay(0.0, 0.0, isOfflineMode = true)
        assertTrue(res is Resource.Error)
        assertTrue(queue.getQueue().isEmpty())
    }

    @Test fun validFixStillReachesTheApi() = runBlocking {
        repo.endDay(26.45, 80.33, accuracyM = 20.0)
        assertEquals(listOf("endWorkday"), calls)
    }

    @Test fun replayOfAlreadyQueuedEntriesIsUnchanged() = runBlocking {
        // Entries already in a device queue keep their old behaviour (sent as-is; the server decides).
        repo.endDay(0.0, 0.0, skipEnqueueOnFailure = true)
        assertEquals(listOf("endWorkday"), calls)
    }
}
