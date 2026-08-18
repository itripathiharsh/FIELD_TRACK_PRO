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
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandLightGray
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.theme.LibreBaskervilleFamily
import com.fieldtrackpro.android.ui.theme.TextPrimary
import com.fieldtrackpro.android.ui.theme.TextSecondary
import java.io.ByteArrayOutputStream

/**
 * Signature capture state holder.
 */
class SignatureCaptureState {
    var paths by mutableStateOf<List<List<Offset>>>(emptyList())
        private set
    private var currentPath = mutableListOf<Offset>()

    fun startPath(offset: Offset) {
        currentPath = mutableListOf(offset)
        paths = paths + listOf(currentPath.toList())
    }

    fun addPoint(offset: Offset) {
        currentPath.add(offset)
        if (paths.isNotEmpty()) {
            paths = paths.dropLast(1) + listOf(currentPath.toList())
        } else {
            paths = listOf(currentPath.toList())
        }
    }

    fun clear() {
        currentPath.clear()
        paths = emptyList()
    }

    val isEmpty: Boolean get() = paths.isEmpty()

    /**
     * Render the signature to a Bitmap, automatically scaling and centering
     * all captured strokes within the target dimensions.
     */
    fun toBitmap(width: Int = 800, height: Int = 400): Bitmap {
        val w = if (width <= 0) 800 else width
        val h = if (height <= 0) 400 else height
        val bitmap = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        canvas.drawColor(android.graphics.Color.WHITE)

        val allPoints = paths.flatten()
        if (allPoints.isEmpty()) return bitmap

        // Calculate bounding box of all drawn points
        var minX = Float.MAX_VALUE
        var maxX = Float.MIN_VALUE
        var minY = Float.MAX_VALUE
        var maxY = Float.MIN_VALUE

        for (pt in allPoints) {
            if (pt.x < minX) minX = pt.x
            if (pt.x > maxX) maxX = pt.x
            if (pt.y < minY) minY = pt.y
            if (pt.y > maxY) maxY = pt.y
        }

        val padding = 32f
        val availableW = (w - 2 * padding).coerceAtLeast(10f)
        val availableH = (h - 2 * padding).coerceAtLeast(10f)

        val strokeW = (maxX - minX).coerceAtLeast(1f)
        val strokeH = (maxY - minY).coerceAtLeast(1f)

        val scale = minOf(availableW / strokeW, availableH / strokeH, 2.0f)
        val offsetX = (w - strokeW * scale) / 2f - minX * scale
        val offsetY = (h - strokeH * scale) / 2f - minY * scale

        val paint = Paint().apply {
            color = android.graphics.Color.parseColor("#14213D")
            style = Paint.Style.STROKE
            strokeWidth = 6f
            strokeCap = Paint.Cap.ROUND
            strokeJoin = Paint.Join.ROUND
            isAntiAlias = true
        }

        for (path in paths) {
            if (path.size > 1) {
                val androidPath = Path()
                val startX = path[0].x * scale + offsetX
                val startY = path[0].y * scale + offsetY
                androidPath.moveTo(startX, startY)
                for (i in 1 until path.size) {
                    val px = path[i].x * scale + offsetX
                    val py = path[i].y * scale + offsetY
                    androidPath.lineTo(px, py)
                }
                canvas.drawPath(androidPath, paint)
            } else if (path.size == 1) {
                val px = path[0].x * scale + offsetX
                val py = path[0].y * scale + offsetY
                canvas.drawCircle(px, py, 4f, paint)
            }
        }
        return bitmap
    }

    /**
     * Verifies that the drawn signature actually contains meaningful non-white, non-transparent strokes.
     */
    fun hasMeaningfulContent(width: Int = 800, height: Int = 400): Boolean {
        if (isEmpty) return false
        val totalPoints = paths.sumOf { it.size }
        if (totalPoints < 3) return false // Reject empty or accidental single taps

        val bitmap = toBitmap(width, height)
        val pixels = IntArray(width * height)
        bitmap.getPixels(pixels, 0, width, 0, 0, width, height)
        var drawnPixels = 0
        for (pixel in pixels) {
            val red = (pixel shr 16) and 0xFF
            val green = (pixel shr 8) and 0xFF
            val blue = pixel and 0xFF
            // If pixel is darker than pure white (#FFFFFF), count it as stroke
            if (red < 240 || green < 240 || blue < 240) {
                drawnPixels++
                if (drawnPixels >= 15) {
                    bitmap.recycle()
                    return true
                }
            }
        }
        bitmap.recycle()
        return false
    }

    fun toPngBytes(width: Int, height: Int): ByteArray {
        val bitmap = toBitmap(width, height)
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

@Composable
fun SignatureCaptureCanvas(
    state: SignatureCaptureState,
    modifier: Modifier = Modifier,
    isReadOnly: Boolean = false
) {
    Canvas(
        modifier = modifier
            .fillMaxWidth()
            .height(200.dp)
            .background(BrandWhite, RoundedCornerShape(10.dp))
            .border(1.5.dp, BrandNavy.copy(alpha = 0.6f), RoundedCornerShape(10.dp))
            .pointerInput(isReadOnly) {
                if (!isReadOnly) {
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
            }
    ) {
        for (path in state.paths) {
            if (path.size > 1) {
                val composePath = androidx.compose.ui.graphics.Path()
                composePath.moveTo(path[0].x, path[0].y)
                for (i in 1 until path.size) {
                    composePath.lineTo(path[i].x, path[i].y)
                }
                drawPath(
                    path = composePath,
                    color = BrandNavy,
                    style = Stroke(
                        width = 4.5.dp.toPx(),
                        cap = StrokeCap.Round,
                        join = StrokeJoin.Round
                    )
                )
            } else if (path.size == 1) {
                drawCircle(
                    color = BrandNavy,
                    radius = 2.5.dp.toPx(),
                    center = path[0]
                )
            }
        }
    }
}

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
            fontFamily = LeagueSpartanFamily,
            fontSize = 15.sp,
            fontWeight = androidx.compose.ui.text.font.FontWeight.Bold,
            color = BrandNavy
        )
        Text(
            text = "Draw signature authorization below",
            fontFamily = LibreBaskervilleFamily,
            fontSize = 12.sp,
            color = TextSecondary
        )

        Spacer(modifier = Modifier.height(8.dp))

        SignatureCaptureCanvas(state = state)

        Spacer(modifier = Modifier.height(8.dp))

        TextButton(onClick = onClear) {
            Text(
                "Clear Signature",
                fontFamily = LeagueSpartanFamily,
                fontWeight = androidx.compose.ui.text.font.FontWeight.Bold,
                fontSize = 13.sp,
                color = BrandNavy
            )
        }
    }
}
