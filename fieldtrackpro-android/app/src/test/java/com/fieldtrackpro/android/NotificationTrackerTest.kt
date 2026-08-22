package com.fieldtrackpro.android

import android.content.SharedPreferences
import com.fieldtrackpro.android.notifications.NotificationTracker
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.lang.reflect.InvocationHandler
import java.lang.reflect.Proxy

class NotificationTrackerTest {

    private val storage = mutableMapOf<String, Any?>()

    @Before
    fun setUp() {
        storage.clear()

        var editorProxy: SharedPreferences.Editor? = null

        val editorHandler = InvocationHandler { _, method, args ->
            when (method.name) {
                "putStringSet" -> {
                    val key = args[0] as String
                    @Suppress("UNCHECKED_CAST")
                    val value = (args[1] as Set<String>).toSet()
                    storage[key] = value
                    editorProxy
                }
                "remove" -> {
                    val key = args[0] as String
                    storage.remove(key)
                    editorProxy
                }
                "clear" -> {
                    storage.clear()
                    editorProxy
                }
                "apply", "commit" -> null
                else -> editorProxy
            }
        }

        editorProxy = Proxy.newProxyInstance(
            SharedPreferences.Editor::class.java.classLoader,
            arrayOf(SharedPreferences.Editor::class.java),
            editorHandler
        ) as SharedPreferences.Editor

        val prefsHandler = InvocationHandler { _, method, args ->
            when (method.name) {
                "getStringSet" -> {
                    val key = args[0] as String
                    @Suppress("UNCHECKED_CAST")
                    val default = args[1] as? Set<String>
                    @Suppress("UNCHECKED_CAST")
                    (storage[key] as? Set<String>) ?: default
                }
                "edit" -> editorProxy
                else -> null
            }
        }

        val fakePrefs = Proxy.newProxyInstance(
            SharedPreferences::class.java.classLoader,
            arrayOf(SharedPreferences::class.java),
            prefsHandler
        ) as SharedPreferences

        NotificationTracker.testPreferences = fakePrefs
    }

    @After
    fun tearDown() {
        NotificationTracker.testPreferences = null
        storage.clear()
    }

    @Test
    fun testNotDeliveredInitially() {
        assertFalse(NotificationTracker.isDelivered(null, "notif_uuid_123"))
    }

    @Test
    fun testMarkDeliveredAndCheck() {
        val notifId = "notif_uuid_456"
        NotificationTracker.markDelivered(null, notifId)
        assertTrue(NotificationTracker.isDelivered(null, notifId))
        assertFalse(NotificationTracker.isDelivered(null, "different_id"))
    }

    @Test
    fun testBulkMarkDelivered() {
        val ids = listOf("id_1", "id_2", "id_3")
        NotificationTracker.markDelivered(null, ids)

        assertTrue(NotificationTracker.isDelivered(null, "id_1"))
        assertTrue(NotificationTracker.isDelivered(null, "id_2"))
        assertTrue(NotificationTracker.isDelivered(null, "id_3"))
        assertFalse(NotificationTracker.isDelivered(null, "id_4"))
    }

    @Test
    fun testClearDelivered() {
        NotificationTracker.markDelivered(null, "id_to_clear")
        assertTrue(NotificationTracker.isDelivered(null, "id_to_clear"))

        NotificationTracker.clear(null)
        assertFalse(NotificationTracker.isDelivered(null, "id_to_clear"))
    }
}
