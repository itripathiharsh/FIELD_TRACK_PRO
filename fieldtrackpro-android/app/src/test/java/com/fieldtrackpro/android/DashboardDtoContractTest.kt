package com.fieldtrackpro.android

import com.fieldtrackpro.android.data.model.DashboardSummaryDto
import com.fieldtrackpro.android.data.model.EmployeeDayDashboardDto
import com.google.gson.Gson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test

class DashboardDtoContractTest {

    private val gson = Gson()

    @Test
    fun dashboardSummaryDto_deserializesFromApiResponse() {
        val json = """
            {
                "period": "LIVE",
                "is_historical": false,
                "kpis": {
                    "total_outlets": 150,
                    "total_sales": 50000.0,
                    "total_collection": 42000.0,
                    "total_market_outstanding": 8000.0,
                    "total_overdue_gt_90": 1200.0,
                    "total_employees": 12,
                    "total_visits": 48,
                    "completed_visits": 20,
                    "pending_visits": 25,
                    "in_progress_visits": 3,
                    "flagged_visits": 2,
                    "gps_verified_visits": 18,
                    "total_exceptions": 4,
                    "pending_exceptions": 1,
                    "total_collections_count": 8,
                    "total_orders_count": 14
                },
                "brand_breakdown": [],
                "fos_breakdown": [],
                "zone_breakdown": [],
                "area_breakdown": [],
                "ageing_distribution": {},
                "recent_exceptions": []
            }
        """.trimIndent()

        val response = gson.fromJson(json, DashboardSummaryDto::class.java)
        assertNotNull(response)
        assertEquals("LIVE", response.period)
        assertEquals(false, response.isHistorical)
        assertEquals(150, response.kpis.totalOutlets)
        assertEquals(48, response.kpis.totalVisits)
        assertEquals(20, response.kpis.completedVisits)
        assertEquals(25, response.kpis.pendingVisits)
        assertEquals(3, response.kpis.inProgressVisits)
        assertEquals(2, response.kpis.flaggedVisits)
    }

    @Test
    fun employeeDayDashboardDto_deserializesFromApiResponse() {
        val json = """
            {
                "employee_id": "e-123",
                "employee_name": "John Rep",
                "assigned_outlets_count": 22,
                "today_visits_count": 10,
                "completed_visits_count": 6,
                "pending_visits_count": 3,
                "in_progress_visits_count": 1,
                "collections_today_count": 2,
                "collections_today_amount": 1500.0,
                "orders_today_count": 4
            }
        """.trimIndent()

        val response = gson.fromJson(json, EmployeeDayDashboardDto::class.java)
        assertNotNull(response)
        assertEquals("e-123", response.employeeId)
        assertEquals("John Rep", response.employeeName)
        assertEquals(22, response.assignedOutletsCount)
        assertEquals(10, response.todayVisitsCount)
        assertEquals(6, response.completedVisitsCount)
        assertEquals(3, response.pendingVisitsCount)
        assertEquals(1, response.inProgressVisitsCount)
        assertEquals(2, response.collectionsTodayCount)
        assertEquals(4, response.ordersTodayCount)
    }
}
