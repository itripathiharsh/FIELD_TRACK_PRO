package com.fieldtrackpro.android

import com.fieldtrackpro.android.data.model.DeviceDto
import com.fieldtrackpro.android.data.model.DeviceRegisterRequest
import com.fieldtrackpro.android.data.model.DeviceUnregisterRequest
import com.google.gson.Gson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class DeviceDtoContractTest {

    private val gson = Gson()

    @Test
    fun testDeviceRegisterRequestSerialization() {
        val request = DeviceRegisterRequest(
            fcmToken = "sample_fcm_token_xyz",
            deviceType = "ANDROID",
            deviceId = "pixel_8_hardware_id"
        )
        val json = gson.toJson(request)

        assertTrue(json.contains("\"fcm_token\":\"sample_fcm_token_xyz\""))
        assertTrue(json.contains("\"device_type\":\"ANDROID\""))
        assertTrue(json.contains("\"device_id\":\"pixel_8_hardware_id\""))
    }

    @Test
    fun testDeviceUnregisterRequestSerialization() {
        val request = DeviceUnregisterRequest(
            fcmToken = "sample_fcm_token_to_remove"
        )
        val json = gson.toJson(request)

        assertTrue(json.contains("\"fcm_token\":\"sample_fcm_token_to_remove\""))
    }

    @Test
    fun testDeviceDtoDeserialization() {
        val json = """
            {
                "id": "11111111-2222-3333-4444-555555555555",
                "user_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "fcm_token": "fcm_payload_token",
                "device_type": "ANDROID",
                "device_id": "dev_01",
                "is_active": true,
                "created_at": "2026-08-22T10:00:00Z",
                "updated_at": "2026-08-22T10:00:00Z",
                "last_used_at": "2026-08-22T10:05:00Z"
            }
        """.trimIndent()

        val dto = gson.fromJson(json, DeviceDto::class.java)

        assertEquals("11111111-2222-3333-4444-555555555555", dto.id)
        assertEquals("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", dto.userId)
        assertEquals("fcm_payload_token", dto.fcmToken)
        assertEquals("ANDROID", dto.deviceType)
        assertEquals("dev_01", dto.deviceId)
        assertTrue(dto.isActive)
        assertEquals("2026-08-22T10:05:00Z", dto.lastUsedAt)
    }
}
