package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.WorkdayApi
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.PendingAction
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.DailyFieldActivitySummaryDto
import com.fieldtrackpro.android.data.model.EmployeeWorkdayResponseDto
import com.fieldtrackpro.android.data.model.WorkSessionDto
import com.fieldtrackpro.android.data.model.WorkSessionEndRequest
import com.fieldtrackpro.android.data.model.WorkSessionStartRequest
import com.google.gson.Gson
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.Response

class WorkdayWorkflowTest {

    private val gson = Gson()

    @Test
    fun workdayModels_serializationAndDeserialization() {
        val json = """
            {
                "employee_id": "emp-123",
                "employee_name": "Rahul Sharma",
                "work_date": "2026-08-30",
                "session": {
                    "id": "sess-456",
                    "employee_id": "emp-123",
                    "work_date": "2026-08-30",
                    "status": "STARTED",
                    "start_time": "2026-08-30T09:15:00Z",
                    "start_latitude": 28.6139,
                    "start_longitude": 77.2090,
                    "start_accuracy_meters": 8.0,
                    "start_notes": "Starting day from office"
                },
                "summary": {
                    "work_date": "2026-08-30",
                    "total_visits": 8,
                    "planned_visits": 6,
                    "adhoc_visits": 2,
                    "completed_visits": 4,
                    "missed_visits": 0,
                    "flagged_visits": 0,
                    "collections_count": 2,
                    "collections_total_amount": 75000.0,
                    "collections_verified_amount": 50000.0
                }
            }
        """.trimIndent()

        val dto = gson.fromJson(json, EmployeeWorkdayResponseDto::class.java)
        assertEquals("emp-123", dto.employeeId)
        assertEquals("Rahul Sharma", dto.employeeName)
        assertEquals("2026-08-30", dto.workDate)
        assertNotNull(dto.session)
        assertEquals("STARTED", dto.session?.status)
        assertEquals(28.6139, dto.session?.startLatitude ?: 0.0, 0.0001)
        assertEquals(77.2090, dto.session?.startLongitude ?: 0.0, 0.0001)
        assertEquals(8.0, dto.session?.startAccuracyMeters ?: 0.0, 0.0001)

        assertEquals(8, dto.summary.totalVisits)
        assertEquals(6, dto.summary.plannedVisits)
        assertEquals(2, dto.summary.adhocVisits)
        assertEquals(75000.0, dto.summary.collectionsTotalAmount, 0.0001)
    }

    @Test
    fun workSessionStartRequest_serialization() {
        val req = WorkSessionStartRequest(
            latitude = 28.6139,
            longitude = 77.2090,
            accuracyMeters = 5.5,
            clientTimestamp = "2026-08-30T09:12:00Z",
            notes = "Start shift"
        )
        val json = gson.toJson(req)
        assertTrue(json.contains("\"latitude\":28.6139"))
        assertTrue(json.contains("\"longitude\":77.209"))
        assertTrue(json.contains("\"accuracy_meters\":5.5"))
    }

    @Test
    fun workSessionEndRequest_serialization() {
        val req = WorkSessionEndRequest(
            latitude = 28.6500,
            longitude = 77.2300,
            accuracyMeters = 7.0,
            clientTimestamp = "2026-08-30T18:42:00Z",
            notes = "End shift"
        )
        val json = gson.toJson(req)
        assertTrue(json.contains("\"latitude\":28.65"))
        assertTrue(json.contains("\"longitude\":77.23"))
        assertTrue(json.contains("\"accuracy_meters\":7.0"))
    }

    @Test
    fun pendingAction_supportsStartDayAndEndDayTypes() {
        val startAction = PendingAction(
            visitId = "workday",
            actionType = "START_DAY",
            latitude = 28.6139,
            longitude = 77.2090,
            accuracyM = 6.0,
            notes = "Start day note"
        )
        val jsonStart = gson.toJson(startAction)
        val deserializedStart = gson.fromJson(jsonStart, PendingAction::class.java)
        assertEquals("START_DAY", deserializedStart.actionType)
        assertEquals("workday", deserializedStart.visitId)
        assertEquals(6.0, deserializedStart.accuracyM ?: 0.0, 0.0001)

        val endAction = PendingAction(
            visitId = "workday",
            actionType = "END_DAY",
            latitude = 28.6800,
            longitude = 77.2900,
            accuracyM = 8.5,
            notes = "End day note"
        )
        val jsonEnd = gson.toJson(endAction)
        val deserializedEnd = gson.fromJson(jsonEnd, PendingAction::class.java)
        assertEquals("END_DAY", deserializedEnd.actionType)
        assertEquals("workday", deserializedEnd.visitId)
        assertEquals(8.5, deserializedEnd.accuracyM ?: 0.0, 0.0001)
    }
}
