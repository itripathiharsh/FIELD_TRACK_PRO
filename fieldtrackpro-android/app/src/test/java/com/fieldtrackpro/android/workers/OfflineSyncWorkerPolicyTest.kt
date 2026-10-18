package com.fieldtrackpro.android.workers

import com.fieldtrackpro.android.data.model.SyncResult
import com.fieldtrackpro.android.workers.OfflineSyncWorker.Outcome
import org.junit.Assert.assertEquals
import org.junit.Test
import java.io.IOException
import java.net.SocketTimeoutException

class OfflineSyncWorkerPolicyTest {

    @Test
    fun cleanRun_isSuccess() {
        assertEquals(Outcome.SUCCESS, OfflineSyncWorker.outcomeFor(SyncResult(2, emptyList())))
    }

    @Test
    fun authPause_isNotReportedAsSuccess() {
        val result = SyncResult(syncedCount = 1, conflicts = emptyList(), pausedForAuth = true)
        assertEquals(Outcome.FAILURE, OfflineSyncWorker.outcomeFor(result))
    }

    @Test
    fun transientFailures_areRetried() {
        val result = SyncResult(syncedCount = 0, conflicts = emptyList(), retryableFailures = 2)
        assertEquals(Outcome.RETRY, OfflineSyncWorker.outcomeFor(result))
    }

    @Test
    fun networkExceptions_alwaysRetry() {
        assertEquals(Outcome.RETRY, OfflineSyncWorker.outcomeForException(IOException("down"), 0))
        assertEquals(Outcome.RETRY, OfflineSyncWorker.outcomeForException(SocketTimeoutException(), 50))
    }

    @Test
    fun nonNetworkExceptions_areCapped() {
        val e = IllegalStateException("bad state")
        assertEquals(Outcome.RETRY, OfflineSyncWorker.outcomeForException(e, 0))
        assertEquals(Outcome.RETRY, OfflineSyncWorker.outcomeForException(e, OfflineSyncWorker.MAX_NON_NETWORK_ATTEMPTS - 1))
        assertEquals(Outcome.FAILURE, OfflineSyncWorker.outcomeForException(e, OfflineSyncWorker.MAX_NON_NETWORK_ATTEMPTS))
    }
}
