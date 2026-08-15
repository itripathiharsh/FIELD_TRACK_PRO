package com.fieldtrackpro.android

import com.fieldtrackpro.android.data.model.CheckInRequest
import com.fieldtrackpro.android.data.model.CheckOutRequest
import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.data.model.GeoPointDto
import com.fieldtrackpro.android.data.model.LocationVerifyResponse
import com.fieldtrackpro.android.data.model.LoginRequest
import com.fieldtrackpro.android.data.model.UserDto
import com.fieldtrackpro.android.data.model.VisitDto
import com.google.gson.Gson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class DtoContractTest {

    private val gson = Gson()

    @Test
    fun loginRequest_serializesCorrectFieldNames() {
        val request = LoginRequest(
            email = "test@example.com",
            mobileNumber = "9876543210",
            password = "secret123"
        )
        val json = gson.toJson(request)
        assertTrue("Should contain email field", json.contains("\"email\""))
        assertTrue("Should contain mobile_number field", json.contains("\"mobile_number\""))
        assertTrue("Should contain password field", json.contains("\"password\""))
        assertTrue("Should NOT contain mobile field", !json.contains("\"mobile\""))
    }

    @Test
    fun loginRequest_withMobileNumber_serializesCorrectly() {
        val request = LoginRequest(
            email = null,
            mobileNumber = "9876543210",
            password = "secret123"
        )
        val json = gson.toJson(request)
        assertTrue("Should contain mobile_number", json.contains("\"mobile_number\":\"9876543210\""))
    }

    @Test
    fun userDto_deserializesFromApiResponse() {
        val json = """
            {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "test@example.com",
                "mobile_number": "9876543210",
                "full_name": "Test User",
                "role": "EMPLOYEE",
                "is_active": true,
                "territory_id": null,
                "employee_id": "550e8400-e29b-41d4-a716-446655440001"
            }
        """.trimIndent()
        val user = gson.fromJson(json, UserDto::class.java)
        assertEquals("550e8400-e29b-41d4-a716-446655440000", user.id)
        assertEquals("test@example.com", user.email)
        assertEquals("9876543210", user.mobileNumber)
        assertEquals("Test User", user.fullName)
        assertEquals("EMPLOYEE", user.role)
        assertEquals(true, user.isActive)
        assertEquals("550e8400-e29b-41d4-a716-446655440001", user.employeeId)
    }

    @Test
    fun customerDto_deserializesNestedLocation() {
        val json = """
            {
                "id": "123",
                "name": "Acme Corp",
                "contact_number": "1234567890",
                "contact_person": "John Doe",
                "address": "123 Main St",
                "location": {
                    "latitude": 12.9716,
                    "longitude": 77.5946
                },
                "geofence_radius_m": 75,
                "territory_id": null,
                "created_by": "550e8400-e29b-41d4-a716-446655440000",
                "created_at": "2026-01-01T00:00:00"
            }
        """.trimIndent()
        val customer = gson.fromJson(json, CustomerDto::class.java)
        assertNotNull("Location should not be null", customer.location)
        assertEquals(12.9716, customer.location.latitude, 0.0001)
        assertEquals(77.5946, customer.location.longitude, 0.0001)
        assertEquals(12.9716, customer.latitude, 0.0001)
        assertEquals(77.5946, customer.longitude, 0.0001)
    }

    @Test
    fun customerDto_nullLocation_accessorsReturnNull() {
        val json = """
            {
                "id": "123",
                "name": "Acme Corp",
                "contact_number": "1234567890",
                "address": "123 Main St",
                "location": null,
                "geofence_radius_m": 75
            }
        """.trimIndent()
        val customer = gson.fromJson(json, CustomerDto::class.java)
        assertNull("Location should be null", customer.location)
    }

    @Test
    fun visitDto_deserializesCorrectFieldNames() {
        val json = """
            {
                "id": "v123",
                "customer_id": "c456",
                "employee_id": "e789",
                "scheduled_at": "2026-01-01T09:00:00",
                "status": "PENDING",
                "check_in_at": null,
                "check_out_at": null,
                "synced": false,
                "created_by": "e789",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00"
            }
        """.trimIndent()
        val visit = gson.fromJson(json, VisitDto::class.java)
        assertEquals("v123", visit.id)
        assertEquals("c456", visit.customerId)
        assertEquals("e789", visit.employeeId)
        assertEquals("PENDING", visit.status)
        assertEquals(false, visit.synced)
    }

    @Test
    fun visitDto_nullableFields_handledCorrectly() {
        val json = """
            {
                "id": "v123",
                "customer_id": "c456",
                "employee_id": "e789",
                "scheduled_at": "2026-01-01T09:00:00",
                "status": "IN_PROGRESS",
                "check_in_at": "2026-01-01T09:05:00",
                "check_out_at": null
            }
        """.trimIndent()
        val visit = gson.fromJson(json, VisitDto::class.java)
        assertEquals("2026-01-01T09:05:00", visit.checkInAt)
        assertNull("checkOutAt should be null", visit.checkOutAt)
    }

    @Test
    fun visitDto_requiredFormFields_deserializeFromVisitRead() {
        val json = """
            {
                "id": "v123",
                "customer_id": "c456",
                "employee_id": "e789",
                "scheduled_at": "2026-01-01T09:00:00",
                "status": "PENDING",
                "required_form_id": "f001",
                "required_form_name": "Sales Visit Form",
                "required_form_status": "PUBLISHED"
            }
        """.trimIndent()
        val visit = gson.fromJson(json, VisitDto::class.java)
        assertEquals("f001", visit.requiredFormId)
        assertEquals("Sales Visit Form", visit.requiredFormName)
        assertEquals("PUBLISHED", visit.requiredFormStatus)
    }

    @Test
    fun visitDto_requiredFormFields_defaultNullWhenAbsent() {
        val json = """
            {
                "id": "v123",
                "customer_id": "c456",
                "employee_id": "e789",
                "scheduled_at": "2026-01-01T09:00:00",
                "status": "PENDING"
            }
        """.trimIndent()
        val visit = gson.fromJson(json, VisitDto::class.java)
        assertNull("requiredFormId should be null when the visit has no required form", visit.requiredFormId)
        assertNull(visit.requiredFormName)
        assertNull(visit.requiredFormStatus)
    }

    @Test
    fun visitDto_clientOnlyFields_notSerialized() {
        val visit = VisitDto(
            id = "v123",
            customerId = "c456",
            employeeId = "e789",
            scheduledAt = "2026-01-01T09:00:00",
            status = "PENDING",
            customerName = "Acme Corp",
            customerAddress = "123 Main St"
        )
        val json = gson.toJson(visit)
        assertTrue("customerName should not appear in JSON", !json.contains("customerName"))
        assertTrue("customerAddress should not appear in JSON", !json.contains("customerAddress"))
    }

    @Test
    fun checkInRequest_serializesCorrectFieldNames() {
        val request = CheckInRequest(
            latitude = 12.9716,
            longitude = 77.5946,
            accuracyM = 10.0,
            isMockLocation = false,
            capturedAt = "2026-08-15T09:30:00Z"
        )
        val json = gson.toJson(request)
        assertTrue("Should contain latitude", json.contains("\"latitude\""))
        assertTrue("Should contain longitude", json.contains("\"longitude\""))
        assertTrue("Should contain accuracy_m", json.contains("\"accuracy_m\""))
        assertTrue("Should contain is_mock_location", json.contains("\"is_mock_location\""))
        assertTrue("Should contain captured_at", json.contains("\"captured_at\""))
    }

    @Test
    fun checkOutRequest_doesNotContainNotesField() {
        val request = CheckOutRequest(
            latitude = 12.9716,
            longitude = 77.5946,
            accuracyM = 10.0,
            isMockLocation = false,
            capturedAt = "2026-08-15T09:30:00Z"
        )
        val json = gson.toJson(request)
        assertTrue("Should NOT contain notes field", !json.contains("notes"))
    }

    @Test
    fun locationVerifyResponse_deserializesCorrectFieldNames() {
        val json = """
            {
                "is_valid": true,
                "distance_m": 45.5,
                "geofence_radius_m": 75.0,
                "is_mock": false,
                "accuracy_m": 10.0,
                "failure_reason": null
            }
        """.trimIndent()
        val response = gson.fromJson(json, LocationVerifyResponse::class.java)
        assertTrue("isValid should be true", response.isValid)
        assertEquals(45.5, response.distanceM, 0.001)
        assertEquals(75.0, response.geofenceRadiusM, 0.001)
        assertEquals(false, response.isMock)
        assertEquals(10.0, response.accuracyM)
        assertNull("failureReason should be null", response.failureReason)
    }

    @Test
    fun geoPointDto_serializesCorrectly() {
        val point = GeoPointDto(latitude = 12.9716, longitude = 77.5946)
        val json = gson.toJson(point)
        assertTrue("Should contain latitude", json.contains("\"latitude\":12.9716"))
        assertTrue("Should contain longitude", json.contains("\"longitude\":77.5946"))
    }
}
