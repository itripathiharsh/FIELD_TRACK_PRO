package com.fieldtrackpro.android.ui.screens.signature

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asAndroidPath
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.io.ByteArrayOutputStream

/**
 * Signature capture state holder.
 */
class SignatureCaptureState {
    var paths = mutableListOf<List<Offset>>()
    private var currentPath = mutableListOf<Offset>()

    fun startPath(offset: Offset) {
        currentPath = mutableListOf(offset)
        paths.add(currentPath)
    }

    fun addPoint(offset: Offset) {
        currentPath.add(offset)
    }

    fun clear() {
        paths.clear()
        currentPath.clear()
    }

    val isEmpty: Boolean get() = paths.isEmpty()

    /**
     * Render the signature to raw PNG bytes. Callers that need a durable
     * on-disk copy (offline safety net) or a raw upload body should use this
     * directly rather than round-tripping through base64 first.
     */
    fun toPngBytes(width: Int, height: Int): ByteArray {
        val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        canvas.drawColor(android.graphics.Color.WHITE)

        val paint = Paint().apply {
            color = android.graphics.Color.BLACK
            style = Paint.Style.STROKE
            strokeWidth = 8f
            strokeCap = Paint.Cap.ROUND
            strokeJoin = Paint.Join.ROUND
            isAntiAlias = true
        }

        for (path in paths) {
            if (path.size > 1) {
                val androidPath = Path()
                androidPath.moveTo(path[0].x, path[0].y)
                for (i in 1 until path.size) {
                    androidPath.lineTo(path[i].x, path[i].y)
                }
                canvas.drawPath(androidPath, paint)
            } else if (path.size == 1) {
                canvas.drawPoint(path[0].x, path[0].y, paint)
            }
        }

        val outputStream = ByteArrayOutputStream()
        bitmap.compress(Bitmap.CompressFormat.PNG, 100, outputStream)
        val bytes = outputStream.toByteArray()
        bitmap.recycle()

        return bytes
    }
}

@Composable
fun rememberSignatureCaptureState(): SignatureCaptureState {
    return remember { SignatureCaptureState() }
}

/**
 * Signature capture canvas component.
 *
 * Allows the user to draw their signature using touch input.
 */
@Composable
fun SignatureCaptureCanvas(
    state: SignatureCaptureState,
    modifier: Modifier = Modifier
) {
    Canvas(
        modifier = modifier
            .fillMaxWidth()
            .height(200.dp)
            .background(Color.White, RoundedCornerShape(8.dp))
            .border(1.dp, Color.Gray, RoundedCornerShape(8.dp))
            .pointerInput(Unit) {
                detectDragGestures(
                    onDragStart = { offset ->
                        state.startPath(offset)
                    },
                    onDrag = { change, _ ->
                        change.consume()
                        state.addPoint(change.position)
                    }
                )
            }
    ) {
        drawIntoCanvas { canvas ->
            val paint = Paint().apply {
                color = android.graphics.Color.BLACK
                style = Paint.Style.STROKE
                strokeWidth = 8f
                strokeCap = Paint.Cap.ROUND
                strokeJoin = Paint.Join.ROUND
                isAntiAlias = true
            }

            for (path in state.paths) {
                if (path.size > 1) {
                    val androidPath = Path()
                    androidPath.moveTo(path[0].x, path[0].y)
                    for (i in 1 until path.size) {
                        androidPath.lineTo(path[i].x, path[i].y)
                    }
                    canvas.nativeCanvas.drawPath(androidPath, paint)
                } else if (path.size == 1) {
                    canvas.nativeCanvas.drawPoint(path[0].x, path[0].y, paint)
                }
            }
        }
    }
}

/**
 * Complete signature capture component with label and instructions.
 */
@Composable
fun SignatureCaptureSection(
    title: String,
    state: SignatureCaptureState,
    onClear: () -> Unit,
    modifier: Modifier = Modifier
) {
    Column(modifier = modifier) {
        Text(
            text = title,
            fontSize = 14.sp,
            fontWeight = androidx.compose.ui.text.font.FontWeight.Bold,
            color = MaterialTheme.colorScheme.onSurface
        )
        Text(
            text = "Sign below using your finger",
            fontSize = 12.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )

        androidx.compose.foundation.layout.Spacer(modifier = Modifier.height(8.dp))

        SignatureCaptureCanvas(state = state)

        androidx.compose.foundation.layout.Spacer(modifier = Modifier.height(8.dp))

        androidx.compose.material3.TextButton(onClick = onClear) {
            Text("Clear Signature", fontSize = 12.sp)
        }
    }
}
