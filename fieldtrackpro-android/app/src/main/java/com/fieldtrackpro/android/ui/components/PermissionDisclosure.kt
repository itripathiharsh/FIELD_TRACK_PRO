package com.fieldtrackpro.android.ui.components

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.LaunchedEffect
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.fieldtrackpro.android.utils.LocationSettingsHelper
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily

/**
 * Prominent in-app disclosure shown BEFORE the system permission prompt (Play "prominent disclosure"
 * requirement). Explains what data is used, why, and when.
 */
enum class PermissionDisclosureKind(
    val title: String,
    val message: String,
    internal val prefKey: String
) {
    LOCATION(
        title = "Location access",
        message = "FieldTrack Pro uses your device's precise location to verify that you are at the " +
            "customer outlet when you check in or out, to record the GPS position of an outlet, and " +
            "to show nearby outlets on the map. Location is captured only when you tap a check-in, " +
            "check-out or capture-location button (and while the map screen is open). The app does not " +
            "track your location in the background.",
        prefKey = "disclosed_location"
    ),
    CAMERA(
        title = "Camera access",
        message = "FieldTrack Pro uses your camera to take photos of the outlet, orders and payment " +
            "proof that you attach to a visit. The camera opens only when you tap the capture button, " +
            "and the photo is uploaded to your company account for that visit.",
        prefKey = "disclosed_camera"
    ),
    NOTIFICATIONS(
        title = "Notifications",
        message = "FieldTrack Pro sends notifications about your visit assignments, plan changes and " +
            "other work updates from your company. No personal location data is used to send them. " +
            "You can turn notifications off at any time in system settings.",
        prefKey = "disclosed_notifications"
    )
}

private const val DISCLOSURE_PREFS = "fieldtrackpro_permission_disclosure"

/** True once the user has acknowledged the disclosure for [kind] (non-sensitive flag, plain prefs). */
fun isDisclosureAcknowledged(context: Context, kind: PermissionDisclosureKind): Boolean =
    try {
        context.getSharedPreferences(DISCLOSURE_PREFS, Context.MODE_PRIVATE).getBoolean(kind.prefKey, false)
    } catch (e: Exception) {
        false
    }

fun markDisclosureAcknowledged(context: Context, kind: PermissionDisclosureKind) {
    try {
        context.getSharedPreferences(DISCLOSURE_PREFS, Context.MODE_PRIVATE)
            .edit().putBoolean(kind.prefKey, true).apply()
    } catch (e: Exception) {
        // Best effort; the dialog will simply show again next time.
    }
}

@Composable
fun PermissionDisclosureDialog(
    kind: PermissionDisclosureKind,
    onContinue: () -> Unit,
    onDismiss: () -> Unit,
    extraMessage: String? = null
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text(kind.title, fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, color = BrandNavy)
        },
        text = {
            Text(if (extraMessage.isNullOrBlank()) kind.message else kind.message + "\n\n" + extraMessage)
        },
        confirmButton = {
            TextButton(onClick = onContinue) {
                Text("CONTINUE", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, color = BrandGold)
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("NOT NOW", fontFamily = LeagueSpartanFamily, color = BrandNavy)
            }
        }
    )
}

/**
 * Wraps a permission-requesting [action]: the first time the returned lambda is invoked for [kind],
 * the disclosure dialog is shown and [action] runs only after the user taps CONTINUE. After that
 * the disclosure is remembered and [action] runs immediately.
 */
@Composable
fun rememberWithDisclosure(kind: PermissionDisclosureKind, action: () -> Unit): () -> Unit {
    val context = LocalContext.current
    val currentAction by rememberUpdatedState(action)
    var showDialog by remember { mutableStateOf(false) }

    if (showDialog) {
        PermissionDisclosureDialog(
            kind = kind,
            onContinue = {
                showDialog = false
                markDisclosureAcknowledged(context, kind)
                currentAction()
            },
            onDismiss = { showDialog = false }
        )
    }

    return remember(kind) {
        {
            if (isDisclosureAcknowledged(context, kind)) currentAction() else showDialog = true
        }
    }
}

/** Pure decision, unit-tested: after a permission request came back denied, was "Don't ask again" chosen? */
object PermissionDenialPolicy {
    /** Android stops showing rationale (shouldShowRequestPermissionRationale == false) once denial is permanent. */
    fun isPermanentlyDenied(granted: Boolean, shouldShowRationale: Boolean): Boolean = !granted && !shouldShowRationale

    fun settingsMessage(kind: PermissionDisclosureKind): String = when (kind) {
        PermissionDisclosureKind.CAMERA ->
            "Camera access is turned off for FieldTrack Pro. To take a photo (for example a payment proof), open the " +
                "app settings, choose Permissions and allow Camera."
        PermissionDisclosureKind.LOCATION ->
            "Location access is turned off for FieldTrack Pro. To check in, check out or capture an outlet position, " +
                "open the app settings, choose Permissions and allow precise Location."
        PermissionDisclosureKind.NOTIFICATIONS ->
            "Notifications are turned off for FieldTrack Pro. To receive visit assignments and plan changes, open " +
                "the app settings and allow Notifications."
    }
}

fun Context.findHostActivity(): Activity? {
    var c: Context? = this
    while (c is ContextWrapper) {
        if (c is Activity) return c
        c = c.baseContext
    }
    return null
}

/** Rationale + "Open app settings" for a permission the user permanently denied. */
@Composable
fun PermissionSettingsDialog(kind: PermissionDisclosureKind, onDismiss: () -> Unit) {
    val context = LocalContext.current
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Permission needed", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, color = BrandNavy) },
        text = { Text(PermissionDenialPolicy.settingsMessage(kind)) },
        confirmButton = {
            TextButton(onClick = {
                onDismiss()
                LocationSettingsHelper.openAppSettings(context)
            }) {
                Text("OPEN APP SETTINGS", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, color = BrandGold)
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("NOT NOW", fontFamily = LeagueSpartanFamily, color = BrandNavy) }
        }
    )
}

/**
 * Returns a function to call from a permission launcher's DENIED result. If the denial is permanent the settings
 * rationale dialog is shown (otherwise nothing: the next tap simply asks again).
 */
@Composable
fun rememberPermissionDeniedHandler(kind: PermissionDisclosureKind, permission: String): () -> Unit {
    val context = LocalContext.current
    var show by remember { mutableStateOf(false) }
    if (show) PermissionSettingsDialog(kind = kind, onDismiss = { show = false })
    return remember(kind, permission) {
        {
            val activity = context.findHostActivity()
            if (activity != null && PermissionDenialPolicy.isPermanentlyDenied(
                    granted = false,
                    shouldShowRationale = ActivityCompat.shouldShowRequestPermissionRationale(activity, permission)
                )
            ) {
                show = true
            }
        }
    }
}

/**
 * Shows the notification disclosure, then the Android 13+ POST_NOTIFICATIONS prompt, once, after the
 * user is signed in ([enabled]). Not requested on cold start before login, and never re-requested
 * after the user has seen the disclosure (avoids nagging).
 */
@Composable
fun NotificationPermissionPrompt(enabled: Boolean, onGranted: () -> Unit) {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return
    val context = LocalContext.current
    var showDialog by remember { mutableStateOf(false) }
    val onDenied = rememberPermissionDeniedHandler(PermissionDisclosureKind.NOTIFICATIONS, Manifest.permission.POST_NOTIFICATIONS)
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) onGranted() else onDenied()
    }

    LaunchedEffect(enabled) {
        if (enabled &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED &&
            !isDisclosureAcknowledged(context, PermissionDisclosureKind.NOTIFICATIONS)
        ) {
            showDialog = true
        }
    }

    if (showDialog) {
        PermissionDisclosureDialog(
            kind = PermissionDisclosureKind.NOTIFICATIONS,
            onContinue = {
                showDialog = false
                markDisclosureAcknowledged(context, PermissionDisclosureKind.NOTIFICATIONS)
                launcher.launch(Manifest.permission.POST_NOTIFICATIONS)
            },
            onDismiss = {
                showDialog = false
                markDisclosureAcknowledged(context, PermissionDisclosureKind.NOTIFICATIONS)
            }
        )
    }
}
