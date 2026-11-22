package com.fieldtrackpro.android.phase3

import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.data.repository.CustomerRepository
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.search.CustomerPortfolioCache
import com.fieldtrackpro.android.search.CustomerSearchController
import com.fieldtrackpro.android.search.CustomerSearchRanker
import com.fieldtrackpro.android.search.CustomerSearchRanker.Tier
import com.fieldtrackpro.android.search.CustomerSources
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class CustomerSearchRankerTest {
    private val list = listOf(
        cust("1", "Agarwal Stores", "OUT-100", address = "Sadar Bazar, Kanpur"),
        cust("2", "Sharma Traders", "OUT-200", address = "Civil Lines"),
        cust("3", "ABC Electronics", "OUT-C5DB", address = "Chandni Chowk, Delhi"),
        cust("4", "ABC Electronics Annexe", "OUT-C5DC"),
        cust("5", "Super Mart", "S-01", address = "Mall Road"),
        cust("6", "Bharat Kirana", "OUT-300", address = "Swaroop Nagar", area = "Swaroop Nagar"),
        cust("7", "New ABC Mobiles", "OUT-400")
    )

    private fun ranked(q: String) = CustomerSearchRanker.rank(list.map { it to true }, q)

    @Test fun exactNameFirstAndCaseInsensitive() {
        for (q in listOf("ABC Electronics", "abc electronics", "  ABC   ELECTRONICS ")) {
            val r = ranked(q)
            assertEquals("3", r.first().customer.id)
            assertEquals(Tier.NAME_EXACT, r.first().tier)
            assertEquals("4", r[1].customer.id) // name starts with
        }
    }

    @Test fun prefixBeforeContainsForAbc() {
        val r = ranked("ABC")
        assertEquals(listOf("3", "4", "7"), r.map { it.customer.id })
        assertEquals(Tier.NAME_CONTAINS, r.last().tier)
    }

    @Test fun singleLetterRanksNamePrefixAboveAddressMatches() {
        val r = ranked("s")
        // Names starting with S come first (Sharma, Super), then names containing s, then address-only.
        assertEquals(listOf("2", "5"), r.take(2).map { it.customer.id })
        val firstAddressOnly = r.indexOfFirst { it.tier == Tier.LOCATION }
        val lastName = r.indexOfLast { it.tier.ordinal <= Tier.NAME_CONTAINS.ordinal }
        assertTrue(firstAddressOnly == -1 || firstAddressOnly > lastName)
    }

    @Test fun codeAndAreaMatches() {
        assertEquals(Tier.CODE_EXACT, ranked("out-300").first().tier)
        assertEquals("6", ranked("out-300").first().customer.id)
        assertEquals(Tier.CODE_PARTIAL, ranked("C5D").first().tier)
        val area = ranked("swaroop")
        assertEquals("6", area.first().customer.id)
        assertEquals(Tier.LOCATION, area.first().tier)
    }

    @Test fun wordOrderAndNoMatch() {
        assertEquals("3", ranked("electronics abc").first().customer.id)
        assertTrue(ranked("zzz-no-such-outlet").isEmpty())
    }

    @Test fun repeatedSearchesAreStable() {
        val a = ranked("a").map { it.customer.id }
        repeat(5) { assertEquals(a, ranked("a").map { it.customer.id }) }
        assertEquals(a, CustomerSearchRanker.rank(list.reversed().map { it to true }, "a").map { it.customer.id })
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class CustomerSearchControllerTest {
    @Before fun clearCache() = CustomerPortfolioCache.clear()

    private fun TestScope.controller(
        portfolio: List<CustomerDto>,
        remote: suspend (String) -> Resource<Pair<List<CustomerDto>, Int>>
    ) = CustomerSearchController(this, { "u1" }, { Resource.Success(portfolio) }, remote)

    @Test fun staleResponseNeverOverwritesANewerQuery() = runTest {
        val slow = CompletableDeferred<Resource<Pair<List<CustomerDto>, Int>>>()
        val c = controller(emptyList()) { q ->
            if (q == "abc") slow.await() else Resource.Success(listOf(cust("9", "ABC Electronics")) to 1)
        }
        c.onQueryChange("abc")
        advanceTimeBy(400); runCurrent()                 // "abc" request in flight
        c.onQueryChange("abc electronics")
        advanceUntilIdle()
        assertEquals(listOf("9"), c.state.value.results.map { it.customer.id })
        slow.complete(Resource.Success(listOf(cust("8", "ABC Old Result")) to 1)) // late answer for the old query
        advanceUntilIdle()
        assertEquals(listOf("9"), c.state.value.results.map { it.customer.id })
    }

    @Test fun typingIsDebouncedIntoOneRequest() = runTest {
        val sent = mutableListOf<String>()
        val c = controller(emptyList()) { q -> sent += q; Resource.Success(emptyList<CustomerDto>() to 0) }
        listOf("a", "ab", "abc", "abc ", "abc e", "abc el").forEach { c.onQueryChange(it); advanceTimeBy(100) }
        advanceUntilIdle()
        assertEquals(listOf("abc el"), sent)
    }

    @Test fun shortQueriesSearchOnlyTheEmployeesOutletsWithoutAnyRequest() = runTest {
        var calls = 0
        val c = controller(listOf(cust("1", "Sharma Traders"), cust("2", "Agarwal Stores", address = "Sadar"))) { calls++; Resource.Success(emptyList<CustomerDto>() to 0) }
        c.start(); advanceUntilIdle()
        c.onQueryChange("s"); advanceUntilIdle()
        assertEquals(0, calls)
        assertEquals("1", c.state.value.results.first().customer.id)
        assertNotNull(c.state.value.hint)
    }

    @Test fun errorsAreShownNotDisguisedAsNoResults() = runTest {
        val c = controller(emptyList()) { Resource.Error("Session expired", 401) }
        c.onQueryChange("abc electronics"); advanceUntilIdle()
        assertEquals("Session expired", c.state.value.error)
    }

    @Test fun exactMatchIsNotLostBehindTheServersAlphabeticalPage() = runTest {
        // Server returns its alphabetical first 50 for "s": names starting with A..R whose ADDRESS contains s.
        val noise = (1..50).map { cust("n$it", "A Outlet $it", address = "Station Road") }
        val sharma = cust("s1", "Sharma Traders")
        val c = controller(listOf(sharma)) { Resource.Success(noise to 4893) }
        c.start(); advanceUntilIdle()
        c.onQueryChange("sha"); advanceUntilIdle()
        assertEquals("s1", c.state.value.results.first().customer.id) // portfolio match ranked first
        assertNotNull(c.state.value.hint)                             // "showing best of 4893"
    }

    @Test fun outOfScopeDirectoryHitsAreFlagged() = runTest {
        val c = controller(listOf(cust("1", "ABC Electronics"))) { Resource.Success(listOf(cust("1", "ABC Electronics"), cust("2", "ABC Electronics")) to 2) }
        c.start(); advanceUntilIdle()
        c.onQueryChange("abc electronics"); advanceUntilIdle()
        val byId = c.state.value.results.associateBy { it.customer.id }
        assertTrue(byId.getValue("1").inScope)
        assertTrue(!byId.getValue("2").inScope)
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class CustomerSourcesTest {
    @Test fun portfolioIsLoadedCompletelyAcrossPages() = runTest {
        val scope = (1..2300).map { cust("c$it", "Outlet %04d".format(it)) }
        val api = FakeCustomerApi(scope)
        val res = CustomerSources.loadPortfolio(CustomerRepository(api.api)) as Resource.Success
        assertEquals(2300, res.data.size)
        assertEquals(listOf("skip=0 limit=1000 search=null", "skip=1000 limit=1000 search=null", "skip=2000 limit=1000 search=null"), api.calls)
    }

    @Test fun directorySearchCarriesTheServerTotal() = runTest {
        val dir = (1..120).map { cust("d$it", "ABC Electronics", code = "OUT-$it") }
        val api = FakeCustomerApi(emptyList(), dir)
        val (rows, total) = (CustomerSources.searchDirectory(CustomerRepository(api.api), "abc electronics") as Resource.Success).data
        assertEquals(50, rows.size)
        assertEquals(120, total)
    }

    @Test fun unauthorizedIsPropagated() = runTest {
        val api = FakeCustomerApi(emptyList(), failWith = 401)
        val res = CustomerSources.loadPortfolio(CustomerRepository(api.api))
        assertTrue(res is Resource.Error && res.code == 401)
        assertNull((res as? Resource.Success)?.data)
    }
}
