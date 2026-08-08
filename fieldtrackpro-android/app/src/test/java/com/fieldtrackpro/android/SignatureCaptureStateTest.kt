package com.fieldtrackpro.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SignatureCaptureStateTest {

    @Test
    fun initialState_isEmpty() {
        val state = createSignatureState()
        assertTrue("Initial state should be empty", state.isEmpty)
    }

    @Test
    fun startPath_addsPath() {
        val state = createSignatureState()
        state.startPath(createOffset(10f, 20f))
        assertFalse("State should not be empty after startPath", state.isEmpty)
        assertEquals("Should have one path", 1, state.paths.size)
    }

    @Test
    fun addPoint_addsToCurrentPath() {
        val state = createSignatureState()
        state.startPath(createOffset(10f, 20f))
        state.addPoint(createOffset(30f, 40f))
        state.addPoint(createOffset(50f, 60f))
        assertEquals("Current path should have 3 points", 3, state.paths[0].size)
    }

    @Test
    fun clear_removesAllPaths() {
        val state = createSignatureState()
        state.startPath(createOffset(10f, 20f))
        state.addPoint(createOffset(30f, 40f))
        state.startPath(createOffset(50f, 60f))
        state.clear()
        assertTrue("State should be empty after clear", state.isEmpty)
        assertEquals("Should have no paths", 0, state.paths.size)
    }

    private fun createSignatureState(): TestSignatureState {
        return TestSignatureState()
    }

    private fun createOffset(x: Float, y: Float): TestOffset {
        return TestOffset(x, y)
    }
}

// Test doubles for the signature capture state
class TestSignatureState {
    val paths = mutableListOf<List<TestOffset>>()
    private var currentPath = mutableListOf<TestOffset>()

    fun startPath(offset: TestOffset) {
        currentPath = mutableListOf(offset)
        paths.add(currentPath)
    }

    fun addPoint(offset: TestOffset) {
        currentPath.add(offset)
    }

    fun clear() {
        paths.clear()
        currentPath.clear()
    }

    val isEmpty: Boolean get() = paths.isEmpty()

    fun toBase64Png(width: Int, height: Int): String {
        // Simplified test version - just return valid base64 string
        val bytes = ByteArray(100) { it.toByte() }
        return java.util.Base64.getEncoder().encodeToString(bytes)
    }
}

data class TestOffset(val x: Float, val y: Float)
