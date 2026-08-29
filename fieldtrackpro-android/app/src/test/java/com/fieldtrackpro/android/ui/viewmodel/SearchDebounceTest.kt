package com.fieldtrackpro.android.ui.viewmodel

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test

/**
 * Unit test for Search Debounce & Query Job Cancellation (APP-PERF-001).
 */
@OptIn(ExperimentalCoroutinesApi::class)
class SearchDebounceTest {

    private val testDispatcher = StandardTestDispatcher()

    @Before
    fun setup() {
        Dispatchers.setMain(testDispatcher)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    /**
     * Test harness demonstrating the 350ms debounce and job cancellation pattern used in VisitsViewModel.
     */
    private class SearchHarness {
        private val _query = MutableStateFlow("")
        val query = _query.asStateFlow()

        var executedSearches = mutableListOf<String>()
        private var searchJob: Job? = null

        fun setSearchQuery(newQuery: String, scope: kotlinx.coroutines.CoroutineScope) {
            _query.value = newQuery
            searchJob?.cancel()
            searchJob = scope.launch {
                delay(350)
                executedSearches.add(newQuery)
            }
        }
    }

    @Test
    fun fastTyping_onlyExecutesFinalQueryAfterDebounceWindow() = runTest {
        val harness = SearchHarness()

        harness.setSearchQuery("S", this)
        advanceTimeBy(100)
        harness.setSearchQuery("Su", this)
        advanceTimeBy(100)
        harness.setSearchQuery("Sup", this)
        advanceTimeBy(100)
        harness.setSearchQuery("Super", this)

        // At 300ms total, no search should have executed yet because each keystroke cancelled the previous job
        assertEquals(0, harness.executedSearches.size)

        // Advance 350ms to let the final debounce timer fire
        advanceTimeBy(360)

        // Exactly one search executed with the final query "Super"
        assertEquals(1, harness.executedSearches.size)
        assertEquals("Super", harness.executedSearches[0])
    }
}
