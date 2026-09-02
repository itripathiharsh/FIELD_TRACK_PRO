package com.fieldtrackpro.android.data.repository

import com.fieldtrackpro.android.data.api.CustomerApi
import com.fieldtrackpro.android.data.local.PendingAction
import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.data.model.GeoPointDto
import com.fieldtrackpro.android.data.model.LocationVerifyRequest
import com.fieldtrackpro.android.data.model.VisitDto
import com.google.gson.Gson
import kotlinx.coroutines.runBlocking
import okhttp3.Headers
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.Response

/**
 * Unit tests for Customer Workflow Remediation.
 *
 * Covers:
 * - APP-CUST-002 / 008 / 009 / 010: Customer pagination, search & X-Total-Count header parsing
 * - APP-CUST-004 / 005 / 019 / 022: VisitDto denormalized customer metadata conversion (no N+1)
 * - APP-CUST-007: LocationVerifyRequest accuracy and mock location preservation
 * - APP-CUST-011: CustomerDto territory_name mapping
 * - APP-CUST-014: PendingAction offline GPS accuracy & mock location persistence
 */
class CustomerWorkflowRemediationTest {

    private val gson = Gson()

    @Test
    fun customerDto_deserializesTerritoryNameAndCoordinates() {
        val json = """
            {
                "id": "cust-123",
                "name": "Acme Store",
                "address": "123 Market Rd",
                "contact_number": "+919876543210",
                "contact_person": "Jane Doe",
                "outlet_code": "ACM-001",
                "dms_code": "DMS-001",
                "territory_id": "terr-1",
                "territory_name": "Bangalore Central",
                "area_id": "area-1",
                "area_name": "Indiranagar",
                "location": {
                    "latitude": 12.9716,
                    "longitude": 77.5946
                },
                "geofence_radius_m": 100
            }
        """.trimIndent()

        val dto = gson.fromJson(json, CustomerDto::class.java)
        assertEquals("cust-123", dto.id)
        assertEquals("Acme Store", dto.name)
        assertEquals("Bangalore Central", dto.territoryName)
        assertEquals("Indiranagar", dto.areaName)
        assertEquals(12.9716, dto.latitude!!, 0.0001)
        assertEquals(77.5946, dto.longitude!!, 0.0001)
        assertEquals(100, dto.geofenceRadiusM)
    }

    @Test
    fun visitDto_toCustomerSummaryDto_constructsCompleteCustomerWithoutNetworkCall() {
        val visit = VisitDto(
            id = "visit-456",
            customerId = "cust-123",
            employeeId = "emp-789",
            scheduledAt = "2026-08-27T10:00:00Z",
            status = "PENDING",
            customerName = "Super Mart",
            customerAddress = "456 Commercial St",
            customerContactNumber = "+919123456780",
            customerContactPerson = "John Manager",
            customerLatitude = 12.9750,
            customerLongitude = 77.6000,
            customerGeofenceRadiusM = 120,
            customerOutletCode = "SUP-002",
            areaName = "MG Road",
            territoryName = "Bangalore East"
        )

        val customer = visit.toCustomerSummaryDto()
        assertEquals("cust-123", customer.id)
        assertEquals("Super Mart", customer.name)
        assertEquals("456 Commercial St", customer.address)
        assertEquals("+919123456780", customer.contactNumber)
        assertEquals("John Manager", customer.contactPerson)
        assertEquals(12.9750, customer.latitude!!, 0.0001)
        assertEquals(77.6000, customer.longitude!!, 0.0001)
        assertEquals(120, customer.geofenceRadiusM)
        assertEquals("SUP-002", customer.outletCode)
        assertEquals("MG Road", customer.areaName)
        assertEquals("Bangalore East", customer.territoryName)
    }

    @Test
    fun customerRepository_parsesXTotalCountHeaderCorrectly() = runBlocking {
        val customersList = listOf(
            CustomerDto(id = "c1", name = "Store 1"),
            CustomerDto(id = "c2", name = "Store 2")
        )
        val headers = Headers.Builder().add("X-Total-Count", "45").build()
        val retrofitResponse = Response.success(customersList, headers)

        val fakeApi = object : CustomerApi {
            override suspend fun getCustomers(
                skip: Int?,
                limit: Int?,
                search: String?,
                territoryId: String?,
                areaId: String?
            ): Response<List<CustomerDto>> {
                return retrofitResponse
            }

            override suspend fun getCustomerById(customerId: String): Response<CustomerDto> {
                throw UnsupportedOperationException()
            }

            override suspend fun proposeCustomerLocation(
                customerId: String,
                proposal: com.fieldtrackpro.android.data.model.LocationProposalCreate
            ): Response<com.fieldtrackpro.android.data.model.LocationProposalDto> {
                throw UnsupportedOperationException()
            }

            override suspend fun getCustomerLocationProposals(
                customerId: String
            ): Response<List<com.fieldtrackpro.android.data.model.LocationProposalDto>> {
                throw UnsupportedOperationException()
            }

            override suspend fun createCustomerProspect(
                prospect: com.fieldtrackpro.android.data.model.CustomerProspectCreate
            ): Response<CustomerDto> {
                throw UnsupportedOperationException()
            }

            override suspend fun getCustomerRequirements(
                customerId: String
            ): Response<List<com.fieldtrackpro.android.data.model.CustomerRequirementDto>> {
                throw UnsupportedOperationException()
            }

            override suspend fun createCustomerRequirement(
                customerId: String,
                req: com.fieldtrackpro.android.data.model.CustomerRequirementCreate
            ): Response<com.fieldtrackpro.android.data.model.CustomerRequirementDto> {
                throw UnsupportedOperationException()
            }

            override suspend fun getBrands(activeOnly: Boolean): Response<List<com.fieldtrackpro.android.data.model.BrandDto>> {
                throw UnsupportedOperationException()
            }

            override suspend fun createBrand(request: com.fieldtrackpro.android.data.model.BrandCreate): Response<com.fieldtrackpro.android.data.model.BrandDto> {
                throw UnsupportedOperationException()
            }
        }

        val repository = CustomerRepository(fakeApi)
        val result = repository.getCustomers(skip = 0, limit = 2)

        assertTrue(result is Resource.Success)
        val page = (result as Resource.Success).data
        assertEquals(2, page.customers.size)
        assertEquals(45, page.totalCount)
        assertEquals(0, page.skip)
        assertEquals(2, page.limit)
        assertTrue(page.hasMore)
    }

    @Test
    fun locationVerifyRequest_serializesAccuracyAndMockFlag() {
        val req = LocationVerifyRequest(
            customerId = "cust-123",
            latitude = 12.9716,
            longitude = 77.5946,
            accuracyM = 12.5,
            isMockLocation = true
        )
        val json = gson.toJson(req)
        assertTrue(json.contains("\"accuracy_m\":12.5"))
        assertTrue(json.contains("\"is_mock_location\":true"))
        assertTrue(json.contains("\"customer_id\":\"cust-123\""))
    }

    @Test
    fun pendingAction_preservesAccuracyAndMockLocationThroughSerialization() {
        val action = PendingAction(
            id = "act-1",
            userId = "user-1",
            visitId = "visit-1",
            actionType = "CHECK_IN",
            latitude = 12.9716,
            longitude = 77.5946,
            timestamp = 1756285200000L,
            accuracyM = 8.5,
            isMockLocation = false,
            notes = "Test notes"
        )
        val json = gson.toJson(action)
        val deserialized = gson.fromJson(json, PendingAction::class.java)

        assertEquals(8.5, deserialized.accuracyM!!, 0.01)
        assertFalse(deserialized.isMockLocation)
        assertEquals("Test notes", deserialized.notes)
        assertEquals("act-1", deserialized.id)
    }

    @Test
    fun customerProspectCreate_serializesWithBrandsAndRequirement() {
        val req = com.fieldtrackpro.android.data.model.CustomerRequirementCreate(
            brand = "USHA",
            requirementType = "Dealership Stock",
            productDetails = "50 Fans",
            quantity = 50,
            expectedValue = 100000.0,
            followUpDate = "2026-09-01"
        )
        val prospect = com.fieldtrackpro.android.data.model.CustomerProspectCreate(
            name = "Test Outlet",
            contactNumber = "+919876543210",
            contactPerson = "Owner",
            gstNumber = "07AAAAA0000A1Z5",
            address = "Main Street",
            brands = listOf("USHA", "Zebronics"),
            requirement = req,
            location = com.fieldtrackpro.android.data.model.GeoPointDto(latitude = 28.6139, longitude = 77.2090),
            gpsAccuracyMeters = 5.0,
            force = false
        )
        val json = gson.toJson(prospect)
        assertTrue(json.contains("\"name\":\"Test Outlet\""))
        assertTrue(json.contains("\"contact_number\":\"+919876543210\""))
        assertTrue(json.contains("\"gst_number\":\"07AAAAA0000A1Z5\""))
        assertTrue(json.contains("\"brands\":[\"USHA\",\"Zebronics\"]"))
        assertTrue(json.contains("\"product_details\":\"50 Fans\""))
        assertTrue(json.contains("\"latitude\":28.6139"))
    }

    @Test
    fun brandDto_serializesAndDeserializesCorrectly() {
        val brand = com.fieldtrackpro.android.data.model.BrandDto(
            id = "brand-uuid-1",
            name = "Panasonic",
            normalizedName = "panasonic",
            isActive = true
        )
        val json = gson.toJson(brand)
        assertTrue(json.contains("\"name\":\"Panasonic\""))
        assertTrue(json.contains("\"is_active\":true"))

        val brandCreate = com.fieldtrackpro.android.data.model.BrandCreate(name = "Panasonic")
        val createJson = gson.toJson(brandCreate)
        assertTrue(createJson.contains("\"name\":\"Panasonic\""))
    }
}
