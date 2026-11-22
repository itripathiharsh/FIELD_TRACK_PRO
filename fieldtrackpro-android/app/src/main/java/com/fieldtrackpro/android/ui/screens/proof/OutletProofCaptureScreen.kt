package com.fieldtrackpro.android.ui.screens.proof

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.location.Location
import android.net.Uri
import android.os.Build
import android.os.Looper
import android.os.SystemClock
import android.provider.Settings
import android.view.Surface
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.window.DialogWindowProvider
import androidx.core.view.WindowCompat
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewmodel.compose.viewModel
import com.fieldtrackpro.android.BuildConfig
import com.fieldtrackpro.android.data.local.OutletProofPayload
import com.fieldtrackpro.android.data.local.OutletProofStore
import com.fieldtrackpro.android.services.LocationCaptureService
import com.fieldtrackpro.android.ui.components.PermissionDisclosureKind
import com.fieldtrackpro.android.ui.components.rememberWithDisclosure
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.utils.AccuracyBand
import com.fieldtrackpro.android.utils.ImageDownsampler
import com.fieldtrackpro.android.utils.LocationSettingsHelper
import com.fieldtrackpro.android.utils.OutletProofRules
import com.fieldtrackpro.android.utils.ProofFix
import com.fieldtrackpro.android.utils.ShutterState
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.util.UUID

enum class CapturePhase { CAPTURING, PROCESSING, REVIEW }

/**
 * State of one capture session. Lives in a ViewModel so a rotation keeps the latest GPS fix, the captured photo and
 * the review state. The GPS fix itself is picked at the shutter click (see [OutletProofCaptureScreen]).
 */
class OutletProofCaptureViewModel : ViewModel() {
    private val _fix = MutableStateFlow<ProofFix?>(null)
    val fix: StateFlow<ProofFix?> = _fix.asStateFlow()

    private val _phase = MutableStateFlow(CapturePhase.CAPTURING)
    val phase: StateFlow<CapturePhase> = _phase.asStateFlow()

    private val _captured = MutableStateFlow<OutletProofPayload?>(null)
    val captured: StateFlow<OutletProofPayload?> = _captured.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    fun onFix(fix: ProofFix) { _fix.value = fix }

    fun beginProcessing() { _error.value = null; _phase.value = CapturePhase.PROCESSING }

    fun onCaptured(payload: OutletProofPayload) { _captured.value = payload; _phase.value = CapturePhase.REVIEW }

    fun onCaptureFailed(message: String) { _error.value = message; _phase.value = CapturePhase.CAPTURING }

    /** Back to the live preview (keeps the GPS fix flowing). */
    fun retake() { _captured.value = null; _error.value = null; _phase.value = CapturePhase.CAPTURING }

    fun reset() { _fix.value = null; retake() }
}

private fun Location.toProofFix(): ProofFix = ProofFix(
    latitude = latitude,
    longitude = longitude,
    accuracyM = if (hasAccuracy()) accuracy else Float.MAX_VALUE,
    elapsedRealtimeMs = elapsedRealtimeNanos / 1_000_000L,
    isMock = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) isMock else {
        @Suppress("DEPRECATION")
        isFromMockProvider
    }
)

private fun Context.findActivity(): Activity? {
    var c: Context? = this
    while (c is ContextWrapper) {
        if (c is Activity) return c
        c = c.baseContext
    }
    return null
}

private fun Context.hasPermission(permission: String) =
    ContextCompat.checkSelfPermission(this, permission) == PackageManager.PERMISSION_GRANTED

/**
 * Entry point used by every screen that needs an outlet proof. Returns a launcher lambda: it shows the camera and
 * location disclosures, requests the permissions (permanent denial offers the app settings), then opens the
 * full-screen live capture. [onCaptured] receives the confirmed bundle (photo path + GPS fix + idempotency key).
 */
@Composable
fun rememberOutletProofCapture(
    customerId: String?,
    outletName: String?,
    onCaptured: (OutletProofPayload) -> Unit
): () -> Unit {
    val context = LocalContext.current
    val captureVm: OutletProofCaptureViewModel = viewModel(key = "outlet_proof_capture_${customerId ?: "new"}")
    var showCapture by rememberSaveable { mutableStateOf(false) }
    var settingsMessage by remember { mutableStateOf<String?>(null) }

    fun hasAll() = context.hasPermission(Manifest.permission.CAMERA) &&
        context.hasPermission(Manifest.permission.ACCESS_FINE_LOCATION)

    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        if (hasAll()) {
            captureVm.reset()
            showCapture = true
        } else {
            val activity = context.findActivity()
            val missing = buildList {
                if (!context.hasPermission(Manifest.permission.CAMERA)) add(Manifest.permission.CAMERA)
                if (!context.hasPermission(Manifest.permission.ACCESS_FINE_LOCATION)) add(Manifest.permission.ACCESS_FINE_LOCATION)
            }
            val permanentlyDenied = activity != null &&
                missing.any { !ActivityCompat.shouldShowRequestPermissionRationale(activity, it) }
            val what = missing.joinToString(" and ") {
                if (it == Manifest.permission.CAMERA) "Camera" else "Precise location"
            }
            if (permanentlyDenied) {
                settingsMessage = "$what permission is turned off. Open the app settings and allow it to take an outlet photo."
            } else {
                Toast.makeText(context, "$what permission is needed to take the outlet photo.", Toast.LENGTH_LONG).show()
            }
        }
    }
    val requestPermissions = rememberWithDisclosure(PermissionDisclosureKind.LOCATION) {
        launcher.launch(
            arrayOf(
                Manifest.permission.CAMERA,
                Manifest.permission.ACCESS_FINE_LOCATION,
                Manifest.permission.ACCESS_COARSE_LOCATION
            )
        )
    }
    val afterCameraDisclosure = rememberWithDisclosure(PermissionDisclosureKind.CAMERA) { requestPermissions() }

    settingsMessage?.let { msg ->
        AlertDialog(
            onDismissRequest = { settingsMessage = null },
            title = { Text("Permission needed", fontWeight = FontWeight.Bold, color = BrandNavy) },
            text = { Text(msg) },
            confirmButton = {
                TextButton(onClick = {
                    settingsMessage = null
                    context.startActivity(
                        Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", context.packageName, null))
                            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    )
                }) { Text("OPEN SETTINGS", fontWeight = FontWeight.Bold, color = BrandGold) }
            },
            dismissButton = { TextButton(onClick = { settingsMessage = null }) { Text("CANCEL", color = BrandNavy) } }
        )
    }

    if (showCapture) {
        Dialog(
            onDismissRequest = { showCapture = false },
            // decorFitsSystemWindows = false: the dialog window draws edge-to-edge and delivers the real status/
            // navigation/cutout insets to Compose. With the default (true) the insets were consumed by the dialog's
            // decor view, so navigationBarsPadding() was 0 and the shutter sat on the gesture bar.
            properties = DialogProperties(
                usePlatformDefaultWidth = false,
                dismissOnClickOutside = false,
                decorFitsSystemWindows = false
            )
        ) {
            OutletProofCaptureScreen(
                vm = captureVm,
                customerId = customerId,
                outletName = outletName,
                onCancel = { showCapture = false },
                onConfirmed = { payload ->
                    showCapture = false
                    onCaptured(payload)
                }
            )
        }
    }

    return {
        if (hasAll()) {
            captureVm.reset()
            showCapture = true
        } else {
            afterCameraDisclosure()
        }
    }
}

/**
 * Full-screen live capture: camera preview, GPS accuracy indicator and a shutter that stays disabled until the
 * latest fix is accurate (<= 30 m), fresh (< 10 s) and not mock. The fix and the capture time are taken at the
 * exact click; photo + fix are ONE bundle. No gallery access anywhere.
 */
@Composable
fun OutletProofCaptureScreen(
    vm: OutletProofCaptureViewModel,
    customerId: String?,
    outletName: String?,
    onCancel: () -> Unit,
    onConfirmed: (OutletProofPayload) -> Unit
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val scope = rememberCoroutineScope()
    val fix by vm.fix.collectAsState()
    val phase by vm.phase.collectAsState()
    val captured by vm.captured.collectAsState()
    val error by vm.error.collectAsState()
    var cameraError by remember { mutableStateOf<String?>(null) }
    // Re-evaluated every second so an aging fix disables the shutter even when no new fix arrives.
    var nowElapsed by remember { mutableLongStateOf(SystemClock.elapsedRealtime()) }
    var locationEnabled by remember { mutableStateOf(true) }
    val locationService = remember { LocationCaptureService(context) }

    LaunchedEffect(Unit) {
        while (true) {
            nowElapsed = SystemClock.elapsedRealtime()
            locationEnabled = locationService.isLocationEnabled()
            delay(500)
        }
    }

    val previewView = remember {
        PreviewView(context).apply {
            implementationMode = PreviewView.ImplementationMode.COMPATIBLE
            scaleType = PreviewView.ScaleType.FILL_CENTER
            keepScreenOn = true
        }
    }
    val imageCapture = remember {
        ImageCapture.Builder().setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY).build()
    }

    // Camera: bound while this screen is shown, released on dispose (also covers rotation re-composition).
    DisposableEffect(lifecycleOwner) {
        val future = ProcessCameraProvider.getInstance(context)
        var provider: ProcessCameraProvider? = null
        future.addListener({
            try {
                val p = future.get()
                provider = p
                val preview = Preview.Builder().build().also { it.setSurfaceProvider(previewView.surfaceProvider) }
                p.unbindAll()
                p.bindToLifecycle(lifecycleOwner, CameraSelector.DEFAULT_BACK_CAMERA, preview, imageCapture)
            } catch (e: Exception) {
                cameraError = "The camera could not be opened on this device."
            }
        }, ContextCompat.getMainExecutor(context))
        onDispose { try { provider?.unbindAll() } catch (_: Exception) {} }
    }

    // High-accuracy location updates while the screen is open (1 s interval).
    DisposableEffect(Unit) {
        val client = LocationServices.getFusedLocationProviderClient(context)
        val request = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 1000L)
            .setMinUpdateIntervalMillis(500L)
            .setWaitForAccurateLocation(false)
            .build()
        val callback = object : LocationCallback() {
            override fun onLocationResult(result: LocationResult) {
                result.lastLocation?.let { vm.onFix(it.toProofFix()) }
            }
        }
        try {
            client.requestLocationUpdates(request, callback, Looper.getMainLooper())
        } catch (e: SecurityException) {
            cameraError = "Location permission is missing."
        }
        onDispose { client.removeLocationUpdates(callback) }
    }

    // Light icons on the dark camera screen (the dialog has its own window, so SystemBarIcons() cannot reach it).
    val hostView = LocalView.current
    val dialogWindow = (hostView.parent as? DialogWindowProvider)?.window
    SideEffect {
        dialogWindow?.let {
            val c = WindowCompat.getInsetsController(it, hostView)
            c.isAppearanceLightStatusBars = false
            c.isAppearanceLightNavigationBars = false
        }
    }

    val shutterState = OutletProofRules.evaluate(fix, nowElapsed)
    val band = OutletProofRules.band(fix?.accuracyM?.takeIf { it != Float.MAX_VALUE })
    val shutterReady = shutterState is ShutterState.Ready && phase == CapturePhase.CAPTURING && cameraError == null

    fun cancel() {
        captured?.photoPath?.let { OutletProofStore.delete(it) }
        vm.reset()
        onCancel()
    }

    fun onShutter() {
        // Pick the freshest fix AT THE CLICK and the device time of the click; both belong to this photo.
        val state = OutletProofRules.evaluate(vm.fix.value, SystemClock.elapsedRealtime())
        val clickFix = (state as? ShutterState.Ready)?.fix ?: return
        val clickWallMs = System.currentTimeMillis()
        vm.beginProcessing()
        val raw = OutletProofStore.newFile(context, "raw")
        previewView.display?.rotation?.let { imageCapture.targetRotation = it } ?: run { imageCapture.targetRotation = Surface.ROTATION_0 }
        imageCapture.takePicture(
            ImageCapture.OutputFileOptions.Builder(raw).build(),
            ContextCompat.getMainExecutor(context),
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                    scope.launch {
                        val result = withContext(Dispatchers.IO) {
                            buildPayload(context, raw, clickFix, clickWallMs, customerId, outletName)
                        }
                        when (result) {
                            is PayloadResult.Ok -> vm.onCaptured(result.payload)
                            is PayloadResult.Failed -> vm.onCaptureFailed(result.userMessage)
                        }
                    }
                }

                override fun onError(exception: ImageCaptureException) {
                    OutletProofStore.delete(raw.absolutePath)
                    vm.onCaptureFailed("The photo could not be taken. Please try again.")
                }
            }
        )
    }

    Box(modifier = Modifier.fillMaxSize().background(Color.Black)) {
        if (phase == CapturePhase.REVIEW && captured != null) {
            ReviewContent(
                payload = captured!!,
                onUse = { onConfirmed(captured!!) },
                onRetake = {
                    captured?.photoPath?.let { OutletProofStore.delete(it) }
                    vm.retake()
                }
            )
        } else {
            CaptureLayout(
                preview = { AndroidView(factory = { previewView }, modifier = Modifier.fillMaxSize()) },
                insets = rememberSystemBarInsets(),
                onCancel = { cancel() },
                band = band,
                fix = fix,
                blockedText = (shutterState as? ShutterState.Blocked)?.let { OutletProofRules.blockMessage(it.reason) },
                locationEnabled = locationEnabled,
                onTurnOnLocation = { LocationSettingsHelper.openLocationSettings(context) },
                errorText = cameraError ?: error,
                shutterReady = shutterReady,
                busy = phase == CapturePhase.PROCESSING,
                onShutter = { onShutter() }
            )
        }
    }
}

sealed class PayloadResult {
    data class Ok(val payload: OutletProofPayload) : PayloadResult()

    /** [stage] is where it failed (for logs/tests); [userMessage] tells the employee what to do. */
    data class Failed(val stage: String, val userMessage: String) : PayloadResult()
}

/** Downsamples (<=1600 px, JPEG q82) into the final private file and bundles it with the click-time fix. */
internal fun buildPayload(
    context: Context,
    raw: File,
    fix: ProofFix,
    clickWallMs: Long,
    customerId: String?,
    outletName: String?
): PayloadResult {
    return try {
        if (!raw.isFile || raw.length() == 0L) {
            return PayloadResult.Failed("CAMERA_FILE", "The camera did not save the photo. Please try again.")
        }
        val bytes = ImageDownsampler.downsample(
            context, Uri.fromFile(raw), OutletProofRules.MAX_LONG_EDGE_PX, OutletProofRules.JPEG_QUALITY
        ) ?: return PayloadResult.Failed("DECODE", "The photo could not be read. Please retake it.")
        val out = OutletProofStore.newFile(context, "proof")
        out.writeBytes(bytes)
        PayloadResult.Ok(
            OutletProofPayload(
                idempotencyKey = UUID.randomUUID().toString(),
                customerId = customerId,
                outletName = outletName,
                photoPath = out.absolutePath,
                latitude = fix.latitude,
                longitude = fix.longitude,
                accuracyM = fix.accuracyM.toDouble(),
                capturedAt = OutletProofRules.isoWithOffset(clickWallMs),
                capturedAtEpochMs = clickWallMs,
                isMock = fix.isMock,
                deviceInfo = Build.MODEL?.take(200)
            )
        )
    } catch (e: java.io.IOException) {
        if (BuildConfig.DEBUG) android.util.Log.w("OutletProofCapture", "save failed: " + e.javaClass.simpleName)
        PayloadResult.Failed("SAVE", "The photo could not be saved. Free some phone storage and try again.")
    } catch (e: Exception) {
        if (BuildConfig.DEBUG) android.util.Log.w("OutletProofCapture", "buildPayload failed: " + e.javaClass.simpleName)
        PayloadResult.Failed("PROCESS", "The photo could not be processed. Please try again.")
    } finally {
        OutletProofStore.delete(raw.absolutePath)
    }
}

@Composable
private fun AccuracyIndicator(band: AccuracyBand, fix: ProofFix?, blockedText: String?) {
    val color = when (band) {
        AccuracyBand.GOOD -> Color(0xFF2E7D32)
        AccuracyBand.FAIR -> Color(0xFFF9A825)
        AccuracyBand.POOR -> Color(0xFFC62828)
        AccuracyBand.NONE -> Color(0xFF757575)
    }
    val accuracyText = when (band) {
        AccuracyBand.NONE -> "GPS: no fix yet"
        else -> "GPS accuracy ±%.0f m".format(fix?.accuracyM ?: 0f)
    }
    Row(
        modifier = Modifier.clip(RoundedCornerShape(20.dp)).background(Color(0xCC000000)).padding(horizontal = 14.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(modifier = Modifier.size(12.dp).clip(CircleShape).background(color))
        Spacer(Modifier.width(8.dp))
        Column {
            Text(accuracyText, color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.Bold)
            if (blockedText != null) Text(blockedText, color = Color(0xFFFFE082), fontSize = 12.sp)
        }
    }
}

@Composable
private fun Shutter(enabled: Boolean, busy: Boolean, onClick: () -> Unit) {
    Box(
        modifier = Modifier
            .size(76.dp)
            .clip(CircleShape)
            .border(4.dp, if (enabled) Color.White else Color(0x66FFFFFF), CircleShape)
            .padding(7.dp)
            .clip(CircleShape)
            .background(if (enabled) Color.White else Color(0x55FFFFFF))
            .clickable(enabled = enabled, onClick = onClick),
        contentAlignment = Alignment.Center
    ) {
        if (busy) {
            CircularProgressIndicator(modifier = Modifier.size(28.dp), strokeWidth = 3.dp, color = BrandNavy)
        } else {
            androidx.compose.material3.Icon(
                androidx.compose.material.icons.Icons.Default.CameraAlt,
                contentDescription = "Take photo",
                tint = if (enabled) BrandNavy else Color(0xCC111827),
                modifier = Modifier.size(30.dp)
            )
        }
    }
}

@Composable
private fun ReviewContent(payload: OutletProofPayload, onUse: () -> Unit, onRetake: () -> Unit) {
    val bitmap by produceState<Bitmap?>(null, payload.photoPath) {
        value = withContext(Dispatchers.IO) {
            payload.photoPath?.let { path ->
                try { ImageDownsampler.decodeSampledBitmapForDisplay(File(path).readBytes(), 1280) } catch (e: Exception) { null }
            }
        }
    }
    Column(modifier = Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing).padding(16.dp)) {
        Box(modifier = Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
            bitmap?.let {
                Image(
                    bitmap = it.asImageBitmap(), contentDescription = "Captured outlet photo",
                    contentScale = ContentScale.Fit, modifier = Modifier.fillMaxSize()
                )
            } ?: CircularProgressIndicator(color = Color.White)
        }
        Spacer(Modifier.padding(4.dp))
        Text(
            "GPS ±%.0f m captured with this photo".format(payload.accuracyM ?: 0.0),
            color = Color.White, fontSize = 13.sp, modifier = Modifier.fillMaxWidth(), textAlign = TextAlign.Center
        )
        Spacer(Modifier.padding(6.dp))
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedButton(onClick = onRetake, modifier = Modifier.weight(1f)) {
                Text("Retake", color = Color.White, fontWeight = FontWeight.Bold)
            }
            Button(
                onClick = onUse, modifier = Modifier.weight(1f),
                colors = ButtonDefaults.buttonColors(containerColor = BrandGold)
            ) { Text("Continue", color = BrandNavy, fontWeight = FontWeight.Bold) }
        }
    }
}

/**
 * The capture screen layout. The preview takes whatever height is LEFT after a control bar that sits fully inside
 * the safe area, so nothing is drawn over the shutter and nothing hides under the gesture/navigation bar.
 */
@Composable
internal fun CaptureLayout(
    preview: @Composable () -> Unit,
    insets: BarInsets,
    onCancel: () -> Unit,
    band: AccuracyBand,
    fix: ProofFix?,
    blockedText: String?,
    locationEnabled: Boolean,
    onTurnOnLocation: () -> Unit,
    errorText: String?,
    shutterReady: Boolean,
    busy: Boolean,
    onShutter: () -> Unit,
) {
    Column(modifier = Modifier.fillMaxSize()) {
        Box(modifier = Modifier.weight(1f).fillMaxWidth()) {
            preview()
            Column(
                modifier = Modifier.fillMaxWidth()
                    .windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Top + WindowInsetsSides.Horizontal))
                    .padding(top = insets.extraTop)
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    TextButton(onClick = onCancel) { Text("CANCEL", color = Color.White, fontWeight = FontWeight.Bold) }
                }
                Text(
                    "Show the shop board and front",
                    color = Color.White,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.Bold,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).background(Color(0x99000000)).padding(10.dp)
                )
            }
        }

        Column(
            // Real system insets (gesture bar OR 3-button bar, any device). If this dialog window does not deliver
            // them to Compose, the window's own raw insets fill the gap (extraBottom); the spacing below is
            // ordinary design padding on top of that, not a device-specific number.
            modifier = Modifier.fillMaxWidth()
                .background(Color(0xFF0B0B0B))
                .windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Bottom + WindowInsetsSides.Horizontal))
                .padding(bottom = insets.extraBottom)
                .padding(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 16.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            AccuracyIndicator(band = band, fix = fix, blockedText = blockedText)
            if (!locationEnabled) {
                Button(
                    onClick = onTurnOnLocation,
                    colors = ButtonDefaults.buttonColors(containerColor = BrandGold)
                ) { Text("Turn on location", color = BrandNavy, fontWeight = FontWeight.Bold) }
            }
            errorText?.let {
                Text(it, color = Color(0xFFFF8A80), fontSize = 13.sp, textAlign = TextAlign.Center)
            }
            if (com.fieldtrackpro.android.BuildConfig.DEBUG) {
                Text("QA build ${com.fieldtrackpro.android.BuildConfig.BUILD_STAMP}", color = Color(0x88FFFFFF), fontSize = 10.sp)
            }
            Shutter(enabled = shutterReady, busy = busy, onClick = onShutter)
        }
    }
}

/** How much extra space the window's raw system-bar insets need beyond what Compose already applies. */
internal data class BarInsets(val extraTop: androidx.compose.ui.unit.Dp, val extraBottom: androidx.compose.ui.unit.Dp)

@Composable
internal fun rememberSystemBarInsets(): BarInsets {
    val view = androidx.compose.ui.platform.LocalView.current
    val density = androidx.compose.ui.platform.LocalDensity.current
    var rawTop by androidx.compose.runtime.remember { androidx.compose.runtime.mutableIntStateOf(0) }
    var rawBottom by androidx.compose.runtime.remember { androidx.compose.runtime.mutableIntStateOf(0) }
    androidx.compose.runtime.DisposableEffect(view) {
        fun read() {
            val i = androidx.core.view.ViewCompat.getRootWindowInsets(view) ?: return
            val bars = i.getInsetsIgnoringVisibility(
                androidx.core.view.WindowInsetsCompat.Type.systemBars() or androidx.core.view.WindowInsetsCompat.Type.displayCutout()
            )
            val gestures = i.getInsets(androidx.core.view.WindowInsetsCompat.Type.mandatorySystemGestures())
            rawTop = bars.top
            rawBottom = maxOf(bars.bottom, gestures.bottom)
        }
        read()
        val l = android.view.ViewTreeObserver.OnGlobalLayoutListener { read() }
        view.viewTreeObserver.addOnGlobalLayoutListener(l)
        onDispose { if (view.viewTreeObserver.isAlive) view.viewTreeObserver.removeOnGlobalLayoutListener(l) }
    }
    val appliedTop = WindowInsets.safeDrawing.getTop(density)
    val appliedBottom = WindowInsets.safeDrawing.getBottom(density)
    return BarInsets(
        extraTop = with(density) { maxOf(0, rawTop - appliedTop).toDp() },
        extraBottom = with(density) { maxOf(0, rawBottom - appliedBottom).toDp() }
    )
}
