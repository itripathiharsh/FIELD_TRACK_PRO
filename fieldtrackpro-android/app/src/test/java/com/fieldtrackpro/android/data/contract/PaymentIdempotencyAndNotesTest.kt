package com.fieldtrackpro.android.data.contract

import com.fieldtrackpro.android.data.model.CheckInRequest
import com.fieldtrackpro.android.data.model.CheckOutRequest
import com.fieldtrackpro.android.data.model.LocationVerifyRequest
import com.fieldtrackpro.android.data.model.PaymentCreateRequest
import com.fieldtrackpro.android.data.model.VisitDto
import com.google.gson.Gson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Contract tests for Payment Idempotency (APP-CONTRACT-003),
 * Checkout Notes (APP-CONTRACT-002), and GPS Accuracy Contract (APP-CONTRACT-001).
 */
class PaymentIdempotencyAndNotesTest {

    private val gson = Gson()

    @Test
    fun paymentCreateRequest_serializesIdempotencyKey() {
        val req = PaymentCreateRequest(
            visitId = "vis-123",
            invoiceId = "inv-456",
            amount = "2500.00",
            paymentMethod = "CHEQUE",
            paymentDate = "2026-08-27",
            chequeNumber = "CHQ-100234",
            chequeBankName = "HDFC Bank",
            notes = "Cheque collected at reception",
            idempotencyKey = "idemp-uuid-7890"
        )
        val json = gson.toJson(req)
        assertTrue(json.contains("\"idempotency_key\":\"idemp-uuid-7890\""))
        assertTrue(json.contains("\"visit_id\":\"vis-123\""))
        assertTrue(json.contains("\"cheque_number\":\"CHQ-100234\""))
    }

    @Test
    fun visitDto_deserializesCheckoutNotes() {
        val json = """
            {
                "id": "vis-100",
                "customer_id": "cust-200",
                "employee_id": "emp-300",
                "scheduled_at": "2026-08-27T10:00:00Z",
                "status": "COMPLETED",
                "notes": "Spoke to store manager, re-order scheduled for Monday."
            }
        """.trimIndent()

        val visit = gson.fromJson(json, VisitDto::class.java)
        assertEquals("vis-100", visit.id)
        assertEquals("Spoke to store manager, re-order scheduled for Monday.", visit.notes)
        assertEquals("COMPLETED", visit.status)
    }

    @Test
    fun checkOutRequest_serializesNotesAndAccuracy() {
        val req = CheckOutRequest(
            latitude = 12.9716,
            longitude = 77.5946,
            accuracyM = 8.5,
            isMockLocation = false,
            capturedAt = "2026-08-27T11:00:00Z",
            idempotencyKey = "checkout-key-1",
            notes = "Completed order verification and signed invoice."
        )
        val json = gson.toJson(req)
        assertTrue(json.contains("\"notes\":\"Completed order verification and signed invoice.\""))
        assertTrue(json.contains("\"accuracy_m\":8.5"))
        assertTrue(json.contains("\"idempotency_key\":\"checkout-key-1\""))
    }

    @Test
    fun checkInRequest_serializesAccuracyCorrectly() {
        val req = CheckInRequest(
            latitude = 12.9716,
            longitude = 77.5946,
            accuracyM = 6.2,
            isMockLocation = false,
            capturedAt = "2026-08-27T10:00:00Z",
            idempotencyKey = "checkin-key-1"
        )
        val json = gson.toJson(req)
        assertTrue(json.contains("\"accuracy_m\":6.2"))
        assertTrue(json.contains("\"is_mock_location\":false"))
    }

    @Test
    fun locationVerifyRequest_serializesAccuracyCorrectly() {
        val req = LocationVerifyRequest(
            customerId = "cust-1",
            latitude = 12.9716,
            longitude = 77.5946,
            accuracyM = 7.1,
            isMockLocation = false
        )
        val json = gson.toJson(req)
        assertTrue(json.contains("\"accuracy_m\":7.1"))
        assertTrue(json.contains("\"customer_id\":\"cust-1\""))
    }
}
