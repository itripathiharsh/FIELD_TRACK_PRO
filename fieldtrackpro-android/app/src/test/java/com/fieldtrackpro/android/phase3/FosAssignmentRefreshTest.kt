package com.fieldtrackpro.android.phase3

import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.search.CustomerPortfolioCache
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test

/**
 * The FOS of an outlet is decided in Tally and synchronised to the backend, which answers GET /customers with
 * exactly the caller's assigned outlets. The phone keeps NO persistent copy of that list (no database), only the
 * in-memory portfolio cache below, so a reassignment reaches an employee as soon as the cache is refreshed:
 * on expiry (10 minutes), on a forced refresh (pull-to-refresh / opening planning), on a user switch or on logout.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class FosAssignmentRefreshTest {
    @Before fun clean() = CustomerPortfolioCache.clear()

    /** What the backend would return for one employee before and after Tally moves outlet "o2" to another FOS. */
    private class Backend {
        var assignedToRaunak = listOf(cust("o1", "Katiyar Watch"), cust("o2", "Sharma Mobiles"))
        var assignedToSahil = listOf(cust("o3", "Gupta Telecom"))
        var calls = 0
        fun forUser(user: String): suspend () -> Resource<List<CustomerDto>> = {
            calls++
            Resource.Success(if (user == "raunak") assignedToRaunak else assignedToSahil)
        }
        fun tallyMovesO2ToSahil() {
            val o2 = assignedToRaunak.first { it.id == "o2" }
            assignedToRaunak = assignedToRaunak.filterNot { it.id == "o2" }
            assignedToSahil = assignedToSahil + o2
        }
    }

    private suspend fun ids(user: String, b: Backend, now: Long, force: Boolean = false): List<String> =
        (CustomerPortfolioCache.get(user, now = now, force = force, load = b.forUser(user)) as Resource.Success).data.map { it.id }

    @Test fun cachedWithinTtlThenReflectsTheNewAssignmentAfterExpiry() = runTest {
        val b = Backend()
        assertEquals(listOf("o1", "o2"), ids("raunak", b, now = 0))
        b.tallyMovesO2ToSahil()
        assertEquals(listOf("o1", "o2"), ids("raunak", b, now = 5 * 60_000L))   // still inside the 10-minute cache
        assertEquals(1, b.calls)
        assertEquals(listOf("o1"), ids("raunak", b, now = 10 * 60_000L + 1))    // expired: the old FOS no longer sees o2
        assertEquals(2, b.calls)
    }

    @Test fun forcedRefreshShowsTheChangeImmediatelyForBothEmployees() = runTest {
        val b = Backend()
        assertEquals(listOf("o1", "o2"), ids("raunak", b, now = 0))
        b.tallyMovesO2ToSahil()
        assertEquals(listOf("o1"), ids("raunak", b, now = 1_000, force = true))
        CustomerPortfolioCache.clear()                                           // a different employee signs in
        assertEquals(listOf("o3", "o2"), ids("sahil", b, now = 2_000))          // the new FOS now sees it
    }

    @Test fun anotherUserNeverSeesTheCachedPortfolioOfThePreviousOne() = runTest {
        val b = Backend()
        assertEquals(listOf("o1", "o2"), ids("raunak", b, now = 0))
        assertEquals(listOf("o3"), ids("sahil", b, now = 1_000))                // same process, different user: reloaded
    }

    @Test fun aFailedRefreshKeepsNothingStaleAndReportsTheError() = runTest {
        val b = Backend()
        ids("raunak", b, now = 0)
        val res = CustomerPortfolioCache.get("raunak", now = 11 * 60_000L) { Resource.Error("Network error: timeout") }
        assertEquals("Network error: timeout", (res as Resource.Error).message)
    }
}
