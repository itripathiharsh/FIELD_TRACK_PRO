package com.fieldtrackpro.android.geofencing

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * P1-8: unit coverage for GeofenceManager.idToRemoveBeforeRegistering - the
 * exact decision GeofenceViewModel.startMonitoring uses to avoid leaving a
 * stale geofence registered when switching visits, and to avoid a needless
 * duplicate registration for the same visit. This is a pure function with no
 * Context/GeofencingClient dependency, so it is tested directly rather than
 * via a hand-copied duplicate.
 */
class GeofenceManagerLifecycleTest {

    @Test
    fun nothingCurrentlyRegistered_nothingToRemove() {
        assertNull(GeofenceManager.idToRemoveBeforeRegistering(currentGeofenceId = null, newGeofenceId = "visit-B"))
    }

    @Test
    fun switchingToADifferentVisit_removesThePreviousOne() {
        assertEquals(
            "visit-A",
            GeofenceManager.idToRemoveBeforeRegistering(currentGeofenceId = "visit-A", newGeofenceId = "visit-B"),
        )
    }

    @Test
    fun reRegisteringTheSameVisit_nothingToRemove() {
        assertNull(GeofenceManager.idToRemoveBeforeRegistering(currentGeofenceId = "visit-A", newGeofenceId = "visit-A"))
    }
}
