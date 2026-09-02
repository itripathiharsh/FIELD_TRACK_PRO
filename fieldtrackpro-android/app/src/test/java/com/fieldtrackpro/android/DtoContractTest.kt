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
        assertEquals(12.9716, customer.location!!.latitude, 0.0001)
        assertEquals(77.5946, customer.location!!.longitude, 0.0001)
        assertEquals(12.9716, customer.latitude!!, 0.0001)
        assertEquals(77.5946, customer.longitude!!, 0.0001)
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
        assertNull("Latitude should be null when location is null", customer.latitude)
        assertNull("Longitude should be null when location is null", customer.longitude)
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

    @Test
    fun visitDto_withReceivedTimestamps_deserializesCorrectly() {
        val json = """
            {
                "id": "v123",
                "customer_id": "c456",
                "employee_id": "e789",
                "scheduled_at": "2026-01-01T09:00:00Z",
                "status": "COMPLETED",
                "check_in_at": "2026-01-01T09:05:00Z",
                "check_in_received_at": "2026-01-01T11:00:00Z",
                "check_out_at": "2026-01-01T09:30:00Z",
                "check_out_received_at": "2026-01-01T11:00:05Z"
            }
        """.trimIndent()
        val visit = gson.fromJson(json, VisitDto::class.java)
        assertEquals("2026-01-01T09:05:00Z", visit.checkInAt)
        assertEquals("2026-01-01T11:00:00Z", visit.checkInReceivedAt)
        assertEquals("2026-01-01T09:30:00Z", visit.checkOutAt)
        assertEquals("2026-01-01T11:00:05Z", visit.checkOutReceivedAt)
    }

    @Test
    fun checkOutRequest_withOptionalIdempotencyKey_serializesCorrectly() {
        val request = CheckOutRequest(
            latitude = 12.9716,
            longitude = 77.5946,
            accuracyM = 8.0,
            isMockLocation = false,
            capturedAt = "2026-08-15T09:30:00Z",
            idempotencyKey = "action-uuid-123"
        )
        val json = gson.toJson(request)
        assertTrue("Should contain idempotency_key", json.contains("\"idempotency_key\":\"action-uuid-123\""))
    }

    @Test
    fun paymentCreateRequest_withBrandAllocations_serializesCorrectly() {
        val request = com.fieldtrackpro.android.data.model.PaymentCreateRequest(
            visitId = "visit-123",
            amount = "80000.00",
            paymentMethod = "ONLINE",
            paymentDate = "2026-08-30",
            utrReference = "UTR99999",
            allocations = listOf(
                com.fieldtrackpro.android.data.model.BrandAllocationInput("USHA", 50000.0),
                com.fieldtrackpro.android.data.model.BrandAllocationInput("Zebronics", 30000.0)
            )
        )
        val json = gson.toJson(request)
        assertTrue("Should contain allocations array", json.contains("\"allocations\":["))
        assertTrue("Should contain USHA allocation", json.contains("\"brand\":\"USHA\""))
        assertTrue("Should contain 50000.0 amount", json.contains("\"amount\":50000.0"))
    }

    @Test
    fun paymentDto_withBrandAllocations_deserializesCorrectly() {
        val json = """
            {
                "id": "pay-123",
                "visit_id": "v-123",
                "customer_id": "c-123",
                "employee_id": "e-123",
                "amount": "80000.00",
                "payment_method": "ONLINE",
                "payment_date": "2026-08-30",
                "status": "PENDING_VERIFICATION",
                "created_at": "2026-08-30T10:00:00Z",
                "allocations": [
                    {
                        "id": "a-1",
                        "payment_id": "pay-123",
                        "brand": "USHA",
                        "allocated_amount": "50000.00"
                    },
                    {
                        "id": "a-2",
                        "payment_id": "pay-123",
                        "brand": "Zebronics",
                        "allocated_amount": "30000.00"
                    }
                ]
            }
        """.trimIndent()
        val dto = gson.fromJson(json, com.fieldtrackpro.android.data.model.PaymentDto::class.java)
        assertEquals("pay-123", dto.id)
        assertEquals(2, dto.allocations.size)
        assertEquals("USHA", dto.allocations[0].brand)
        assertEquals("50000.00", dto.allocations[0].allocatedAmount)
        assertEquals("Zebronics", dto.allocations[1].brand)
        assertEquals("30000.00", dto.allocations[1].allocatedAmount)
    }

    @Test
    fun adHocVisitCreateRequest_serializesCorrectly() {
        val request = com.fieldtrackpro.android.data.model.AdHocVisitCreateRequest(
            customerId = "cust-456",
            adhocReason = "Payment Follow-up",
            adhocNotes = "Urgent cheque collection"
        )
        val json = gson.toJson(request)
        assertTrue("Should contain customer_id", json.contains("\"customer_id\":\"cust-456\""))
        assertTrue("Should contain adhoc_reason", json.contains("\"adhoc_reason\":\"Payment Follow-up\""))
        assertTrue("Should contain adhoc_notes", json.contains("\"adhoc_notes\":\"Urgent cheque collection\""))
    }

    @Test
    fun visitDto_withAdHocFields_deserializesCorrectly() {
        val json = """
            {
                "id": "v-adhoc-1",
                "customer_id": "c-1",
                "employee_id": "e-1",
                "scheduled_at": "2026-08-30T10:00:00Z",
                "status": "PENDING",
                "visit_type": "AD_HOC",
                "adhoc_reason": "Customer Requested",
                "adhoc_notes": "Urgent on-site demo requested by store owner"
            }
        """.trimIndent()
        val dto = gson.fromJson(json, VisitDto::class.java)
        assertEquals("v-adhoc-1", dto.id)
        assertEquals("AD_HOC", dto.visitType)
        assertTrue(dto.isAdHoc)
        assertEquals("Customer Requested", dto.adhocReason)
        assertEquals("Urgent on-site demo requested by store owner", dto.adhocNotes)
    }
}
