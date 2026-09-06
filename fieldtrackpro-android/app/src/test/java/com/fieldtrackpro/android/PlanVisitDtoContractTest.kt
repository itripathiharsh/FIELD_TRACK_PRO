package com.fieldtrackpro.android

import com.fieldtrackpro.android.data.model.EmployeeMonthlyAnalyticsDto
import com.fieldtrackpro.android.data.model.MonthlyVisitPlanDto
import com.fieldtrackpro.android.data.model.PlannedVisitCreateRequest
import com.fieldtrackpro.android.data.model.PlannedVisitDto
import com.fieldtrackpro.android.data.model.PlannedVisitRescheduleRequest
import com.fieldtrackpro.android.data.model.PlannedVisitUpdateRequest
import com.google.gson.Gson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PlanVisitDtoContractTest {

    private val gson = Gson()

    @Test
    fun plannedVisitCreateRequest_serializesCorrectFieldNames() {
        val request = PlannedVisitCreateRequest(
            customerId = "4385f5f4-6b41-4dd2-ae54-62e9769f0ddd",
            plannedDate = "2026-09-15",
            visitType = "PLANNED",
            priority = "HIGH",
            notes = "Payment follow-up"
        )
        val json = gson.toJson(request)
        assertTrue("Should contain customer_id", json.contains("\"customer_id\":\"4385f5f4-6b41-4dd2-ae54-62e9769f0ddd\""))
        assertTrue("Should contain planned_date", json.contains("\"planned_date\":\"2026-09-15\""))
        assertTrue("Should contain visit_type", json.contains("\"visit_type\":\"PLANNED\""))
        assertTrue("Should contain priority", json.contains("\"priority\":\"HIGH\""))
        assertTrue("Should contain notes", json.contains("\"notes\":\"Payment follow-up\""))
    }

    @Test
    fun plannedVisitUpdateRequest_serializesCorrectFieldNames() {
        val request = PlannedVisitUpdateRequest(
            priority = "LOW",
            notes = "Updated notes",
            visitType = "AD_HOC"
        )
        val json = gson.toJson(request)
        assertTrue(json.contains("\"priority\":\"LOW\""))
        assertTrue(json.contains("\"notes\":\"Updated notes\""))
        assertTrue(json.contains("\"visit_type\":\"AD_HOC\""))
    }

    @Test
    fun plannedVisitRescheduleRequest_serializesCorrectFieldNames() {
        val request = PlannedVisitRescheduleRequest(newDate = "2026-09-20")
        val json = gson.toJson(request)
        assertTrue(json.contains("\"new_date\":\"2026-09-20\""))
    }

    @Test
    fun plannedVisitDto_deserializesFromApiResponse() {
        val json = """
            {
                "id": "e0a12345-6789-4abc-def0-1234567890ab",
                "monthly_plan_id": "379bf062-46df-4ea5-8ab9-2b69fc4f43df",
                "employee_id": "99f25cb5-42af-4b25-a06f-94ac5b473ba6",
                "customer_id": "4385f5f4-6b41-4dd2-ae54-62e9769f0ddd",
                "planned_date": "2026-09-15",
                "visit_type": "PLANNED",
                "priority": "HIGH",
                "notes": "Payment collection and stock audit",
                "status": "PLANNED",
                "created_at": "2026-09-05T17:00:00Z",
                "updated_at": "2026-09-05T17:00:00Z",
                "customer_name": "New Jagdish Brothers",
                "customer_outlet_code": "SGRGUS1463",
                "customer_address": "Main Market, Kanpur",
                "employee_name": "Sahil Verma",
                "employee_code": "EMP001",
                "area_name": "Kanpur Central",
                "territory_name": "UP Central"
            }
        """.trimIndent()

        val dto = gson.fromJson(json, PlannedVisitDto::class.java)
        assertNotNull(dto)
        assertEquals("e0a12345-6789-4abc-def0-1234567890ab", dto.id)
        assertEquals("New Jagdish Brothers", dto.customerName)
        assertEquals("SGRGUS1463", dto.customerOutletCode)
        assertEquals("HIGH", dto.priority)
        assertEquals("PLANNED", dto.status)
        assertEquals("2026-09-15", dto.plannedDate)
        assertEquals("Sahil Verma", dto.employeeName)
    }

    @Test
    fun monthlyVisitPlanDto_deserializesFromApiResponse() {
        val json = """
            {
                "id": "379bf062-46df-4ea5-8ab9-2b69fc4f43df",
                "employee_id": "99f25cb5-42af-4b25-a06f-94ac5b473ba6",
                "year": 2026,
                "month": 9,
                "status": "ACTIVE",
                "notes": "Target: 40 beat visits",
                "employee_name": "Sahil Verma",
                "employee_code": "EMP001",
                "total_planned_visits": 5,
                "active_days_count": 4,
                "planned_visits": [
                    {
                        "id": "e0a12345-6789-4abc-def0-1234567890ab",
                        "monthly_plan_id": "379bf062-46df-4ea5-8ab9-2b69fc4f43df",
                        "employee_id": "99f25cb5-42af-4b25-a06f-94ac5b473ba6",
                        "customer_id": "4385f5f4-6b41-4dd2-ae54-62e9769f0ddd",
                        "planned_date": "2026-09-15",
                        "visit_type": "PLANNED",
                        "priority": "HIGH",
                        "notes": "Audit",
                        "status": "PLANNED",
                        "customer_name": "New Jagdish Brothers"
                    }
                ]
            }
        """.trimIndent()

        val plan = gson.fromJson(json, MonthlyVisitPlanDto::class.java)
        assertNotNull(plan)
        assertEquals(2026, plan.year)
        assertEquals(9, plan.month)
        assertEquals("ACTIVE", plan.status)
        assertEquals(5, plan.totalPlannedVisits)
        assertEquals(4, plan.activeDaysCount)
        assertEquals(1, plan.plannedVisits.size)
        assertEquals("New Jagdish Brothers", plan.plannedVisits[0].customerName)
    }

    @Test
    fun employeeMonthlyAnalyticsDto_deserializesFromApiResponse() {
        val json = """
            {
                "employee_id": "99f25cb5-42af-4b25-a06f-94ac5b473ba6",
                "employee_name": "Sahil Verma",
                "employee_code": "EMP001",
                "year": 2026,
                "month": 9,
                "total_planned": 10,
                "completed": 7,
                "missed": 1,
                "cancelled": 0,
                "extra_unplanned": 2,
                "completion_rate": 70.0,
                "active_planned_days": 6,
                "active_execution_days": 5,
                "behind_schedule": false
            }
        """.trimIndent()

        val analytics = gson.fromJson(json, EmployeeMonthlyAnalyticsDto::class.java)
        assertNotNull(analytics)
        assertEquals(10, analytics.totalPlanned)
        assertEquals(7, analytics.completed)
        assertEquals(70.0, analytics.completionRate!!, 0.001)
        assertEquals(false, analytics.behindSchedule)
    }
}
