package com.fieldtrackpro.android.geofencing

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class GeofenceStateTest {

    @Before
    fun setup() {
        GeofenceStateHolder.clear()
    }

    @Test
    fun geofenceState_defaultIsUnknown() {
        assertEquals(GeofenceState.UNKNOWN, GeofenceStateHolder.getState("any-id"))
    }

    @Test
    fun geofenceState_enterSetsInside() {
        GeofenceStateHolder.updateState("visit-1", GeofenceState.INSIDE)
        assertEquals(GeofenceState.INSIDE, GeofenceStateHolder.getState("visit-1"))
    }

    @Test
    fun geofenceState_exitSetsOutside() {
        GeofenceStateHolder.updateState("visit-1", GeofenceState.OUTSIDE)
        assertEquals(GeofenceState.OUTSIDE, GeofenceStateHolder.getState("visit-1"))
    }

    @Test
    fun geofenceState_multipleVisitsTrackedIndependently() {
        GeofenceStateHolder.updateState("visit-1", GeofenceState.INSIDE)
        GeofenceStateHolder.updateState("visit-2", GeofenceState.OUTSIDE)

        assertEquals(GeofenceState.INSIDE, GeofenceStateHolder.getState("visit-1"))
        assertEquals(GeofenceState.OUTSIDE, GeofenceStateHolder.getState("visit-2"))
    }

    @Test
    fun geofenceState_updateOverwritesPrevious() {
        GeofenceStateHolder.updateState("visit-1", GeofenceState.INSIDE)
        GeofenceStateHolder.updateState("visit-1", GeofenceState.OUTSIDE)

        assertEquals(GeofenceState.OUTSIDE, GeofenceStateHolder.getState("visit-1"))
    }

    @Test
    fun geofenceState_listenerNotified() {
        var notifiedId: String? = null
        var notifiedState: GeofenceState? = null

        GeofenceStateHolder.addListener { id, state ->
            notifiedId = id
            notifiedState = state
        }

        GeofenceStateHolder.updateState("visit-1", GeofenceState.INSIDE)

        assertEquals("visit-1", notifiedId)
        assertEquals(GeofenceState.INSIDE, notifiedState)
    }

    @Test
    fun geofenceState_listenerCanBeRemoved() {
        var callCount = 0

        val listener: (String, GeofenceState) -> Unit = { _, _ -> callCount++ }

        GeofenceStateHolder.addListener(listener)
        GeofenceStateHolder.updateState("visit-1", GeofenceState.INSIDE)
        assertEquals(1, callCount)

        GeofenceStateHolder.removeListener(listener)
        GeofenceStateHolder.updateState("visit-2", GeofenceState.OUTSIDE)
        assertEquals(1, callCount) // should not increase
    }

    @Test
    fun geofenceState_clearRemovesAll() {
        GeofenceStateHolder.updateState("visit-1", GeofenceState.INSIDE)
        GeofenceStateHolder.updateState("visit-2", GeofenceState.OUTSIDE)

        GeofenceStateHolder.clear()

        assertEquals(GeofenceState.UNKNOWN, GeofenceStateHolder.getState("visit-1"))
        assertEquals(GeofenceState.UNKNOWN, GeofenceStateHolder.getState("visit-2"))
    }
}
