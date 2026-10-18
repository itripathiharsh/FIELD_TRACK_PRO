package com.fieldtrackpro.android.ui.viewmodel

import com.fieldtrackpro.android.data.api.CollectionApi
import com.fieldtrackpro.android.data.local.InMemorySharedPreferences
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.PaymentCreateRequest
import com.fieldtrackpro.android.data.model.PaymentDto
import com.fieldtrackpro.android.data.repository.CollectionRepository
import com.fieldtrackpro.android.data.repository.FakeCollectionApi
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.Response
import java.io.IOException

@OptIn(ExperimentalCoroutinesApi::class)
class CollectionViewModelResetTest {

    @Before fun setUp() = Dispatchers.setMain(UnconfinedTestDispatcher())
    @After fun tearDown() = Dispatchers.resetMain()

    private class GatedApi(val delegate: FakeCollectionApi, val gate: CompletableDeferred<Unit>) : CollectionApi by delegate {
        override suspend fun createPayment(request: PaymentCreateRequest): Response<PaymentDto> {
            gate.await()
            return delegate.createPayment(request)
        }
    }

    private fun tokens() = TokenManager(null, InMemorySharedPreferences()).apply {
        saveTokens("a", "r"); saveUserProfile("N", null, "EMPLOYEE", id = "u1")
    }

    private fun vm(api: CollectionApi, queue: OfflineQueueManager) =
        CollectionViewModel(tokenManager = tokens(), customRepository = CollectionRepository(api), offlineQueueManager = queue)

    private fun submit(vm: CollectionViewModel, onSubmitted: () -> Unit = {}) = vm.submitCollection(
        visitId = "v1", invoiceId = null, amount = "100.0", paymentMethod = "CASH", paymentDate = "2026-10-10",
        customerId = "c1", outletName = "S", onSubmitted = { onSubmitted() }
    )

    /** The durable queue write runs on Dispatchers.IO (real thread), so wait (real time) for the submit to settle. */
    private fun settle(vm: CollectionViewModel) {
        val deadline = System.currentTimeMillis() + 5000
        while (vm.collectionState.value is CollectionState.Submitting && System.currentTimeMillis() < deadline) Thread.sleep(10)
    }

    @Test
    fun savedOfflineState_isClearedOnReset_soTheNextFormStartsClean() = runTest {
        val api = FakeCollectionApi().apply { createThrows = IOException("offline") }
        val queue = OfflineQueueManager(InMemorySharedPreferences())
        val vm = vm(api, queue)
        submit(vm)
        settle(vm)
        assertTrue(vm.collectionState.value is CollectionState.SavedOffline)

        vm.resetCollectionState() // what leaving the form (system Back) triggers

        assertEquals(CollectionState.Idle, vm.collectionState.value)
        // and the next submission is a NEW payment with a NEW idempotency key
        api.createThrows = IOException("offline")
        submit(vm)
        settle(vm)
        val keys = queue.getQueue().mapNotNull { it.paymentPayload?.idempotencyKey }
        assertEquals(2, keys.size)
        assertNotEquals(keys[0], keys[1])
    }

    @Test
    fun rejectedSubmit_keepsTheKeyForTheRetryOfTheSameForm() = runTest {
        val api = FakeCollectionApi()
        api.createBehavior = { api.err(422, """{"error":{"message":"bad"}}""") }
        val vm = vm(api, OfflineQueueManager(InMemorySharedPreferences()))
        submit(vm)
        submit(vm)
        assertEquals(2, api.createCalls.size)
        assertEquals("same in-flight form reuses its key", api.createCalls[0].idempotencyKey, api.createCalls[1].idempotencyKey)
    }

    @Test
    fun submissionFinishingAfterTheFormWasLeft_doesNotLeakIntoTheNextForm() = runTest {
        val gate = CompletableDeferred<Unit>()
        val fake = FakeCollectionApi()
        val vm = vm(GatedApi(fake, gate), OfflineQueueManager(InMemorySharedPreferences()))
        var navigatedBack = 0
        submit(vm) { navigatedBack++ }
        assertEquals(CollectionState.Submitting, vm.collectionState.value)

        vm.resetCollectionState() // user pressed system Back while the request was in flight
        gate.complete(Unit)       // the request completes afterwards

        assertEquals("stale result must not overwrite the next form's state", CollectionState.Idle, vm.collectionState.value)
        assertEquals("stale completion must not pop an unrelated screen", 0, navigatedBack)
        assertFalse(vm.collectionState.value is CollectionState.Success)
        assertEquals("the payment itself was still created", 1, fake.createCalls.size)
    }
}
