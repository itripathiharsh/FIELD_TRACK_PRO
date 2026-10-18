package com.fieldtrackpro.android.workers

import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import com.fieldtrackpro.android.data.model.SyncResult
import com.fieldtrackpro.android.ui.components.PermissionDenialPolicy
import com.fieldtrackpro.android.ui.components.PermissionDisclosureKind
import com.fieldtrackpro.android.workers.OfflineSyncWorker.Outcome
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SchedulerAndPermissionPolicyTest {

    // ------------------------------------------------------------------ scheduler never cancels in-flight work

    @Test
    fun enqueueAndActivityStart_neverUseReplace() {
        assertNotEquals(ExistingWorkPolicy.REPLACE, OfflineSyncScheduler.ENQUEUE_POLICY)
        assertEquals(ExistingWorkPolicy.APPEND_OR_REPLACE, OfflineSyncScheduler.ENQUEUE_POLICY)
        assertEquals(ExistingWorkPolicy.KEEP, OfflineSyncScheduler.ENSURE_POLICY)
        assertEquals(ExistingPeriodicWorkPolicy.KEEP, OfflineSyncScheduler.PERIODIC_POLICY)
    }

    @Test
    fun onlyExplicitSyncNow_mayReplace() {
        assertEquals(ExistingWorkPolicy.REPLACE, OfflineSyncScheduler.SYNC_NOW_POLICY)
    }

    // ------------------------------------------------------------------ worker outcome for auth pauses

    @Test
    fun auth401WithSessionStillStored_isRetriedWithBackoff_notFailed() {
        val r = SyncResult(syncedCount = 0, conflicts = emptyList(), pausedForAuth = true)
        assertEquals(Outcome.RETRY, OfflineSyncWorker.outcomeFor(r, sessionStillValid = true, runAttemptCount = 0))
    }

    @Test
    fun auth401WithSessionGone_isFailure() {
        val r = SyncResult(syncedCount = 0, conflicts = emptyList(), pausedForAuth = true)
        assertEquals(Outcome.FAILURE, OfflineSyncWorker.outcomeFor(r, sessionStillValid = false))
        assertEquals(Outcome.FAILURE, OfflineSyncWorker.outcomeFor(r)) // default: not valid
    }

    @Test
    fun auth401RetriesAreCapped() {
        val r = SyncResult(syncedCount = 0, conflicts = emptyList(), pausedForAuth = true)
        assertEquals(Outcome.RETRY, OfflineSyncWorker.outcomeFor(r, true, OfflineSyncWorker.MAX_AUTH_RETRIES - 1))
        assertEquals(Outcome.FAILURE, OfflineSyncWorker.outcomeFor(r, true, OfflineSyncWorker.MAX_AUTH_RETRIES))
    }

    @Test
    fun passwordChangePending_pausesQuietly_notFailureNotRetryLoop() {
        val r = SyncResult(0, emptyList(), pausedForAuth = true, pausedForPasswordChange = true)
        assertEquals(Outcome.SUCCESS, OfflineSyncWorker.outcomeFor(r, sessionStillValid = true))
        assertEquals(Outcome.SUCCESS, OfflineSyncWorker.outcomeFor(r, sessionStillValid = false))
    }

    // ------------------------------------------------------------------ permanent permission denial

    @Test
    fun permanentDenial_isDeniedWithoutRationale() {
        assertTrue(PermissionDenialPolicy.isPermanentlyDenied(granted = false, shouldShowRationale = false))
        assertFalse("first denial can still be re-asked", PermissionDenialPolicy.isPermanentlyDenied(false, true))
        assertFalse(PermissionDenialPolicy.isPermanentlyDenied(true, false))
    }

    @Test
    fun settingsRationale_existsForCameraLocationAndNotifications() {
        PermissionDisclosureKind.values().forEach {
            val msg = PermissionDenialPolicy.settingsMessage(it)
            assertTrue(it.name, msg.contains("settings", ignoreCase = true))
        }
        assertTrue(PermissionDenialPolicy.settingsMessage(PermissionDisclosureKind.CAMERA).contains("Camera"))
        assertTrue(PermissionDenialPolicy.settingsMessage(PermissionDisclosureKind.LOCATION).contains("Location"))
        assertTrue(PermissionDenialPolicy.settingsMessage(PermissionDisclosureKind.NOTIFICATIONS).contains("Notifications"))
    }
}
