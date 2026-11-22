package com.fieldtrackpro.android.update

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.withContext
import java.io.File

sealed class InstallEvent {
    object AwaitingUserConfirmation : InstallEvent()
    object Succeeded : InstallEvent()
    object CancelledByUser : InstallEvent()
    data class Failed(val message: String) : InstallEvent()
}

/**
 * Hands a verified APK to Android's PackageInstaller.
 *
 * Android always shows its own confirmation for an app that is not a system installer; on Android 12+ the session
 * additionally REQUIRES user action ([PackageInstaller.SessionParams.USER_ACTION_REQUIRED]), so an update is never
 * installed silently. Android also refuses an update signed with a different key or with a lower versionCode.
 */
object UpdateInstaller {
    const val ACTION_INSTALL_STATUS = "com.fieldtrackpro.android.action.UPDATE_INSTALL_STATUS"

    private val _events = MutableSharedFlow<InstallEvent>(extraBufferCapacity = 4)
    val events: SharedFlow<InstallEvent> = _events.asSharedFlow()

    internal fun emit(event: InstallEvent) {
        _events.tryEmit(event)
    }

    /** Android 8+: the user must allow "Install unknown apps" for FieldTrack Pro once. */
    fun canRequestInstalls(context: Context): Boolean =
        context.packageManager.canRequestPackageInstalls()

    fun installPermissionSettingsIntent(context: Context): Intent =
        Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${context.packageName}"))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

    suspend fun install(context: Context, apk: File) = withContext(Dispatchers.IO) {
        val installer = context.packageManager.packageInstaller
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL).apply {
            setAppPackageName(context.packageName)
            setSize(apk.length())
            if (Build.VERSION.SDK_INT >= 31) setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_REQUIRED)
        }
        val sessionId = installer.createSession(params)
        try {
            installer.openSession(sessionId).use { session ->
                session.openWrite("fieldtrackpro.apk", 0, apk.length()).use { out ->
                    apk.inputStream().use { it.copyTo(out, 64 * 1024) }
                    session.fsync(out)
                }
                val callback = Intent(ACTION_INSTALL_STATUS).setPackage(context.packageName)
                val flags = PendingIntent.FLAG_UPDATE_CURRENT or
                    (if (Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0)
                val pending = PendingIntent.getBroadcast(context, sessionId, callback, flags)
                session.commit(pending.intentSender)
            }
        } catch (e: Exception) {
            runCatching { installer.abandonSession(sessionId) }
            throw e
        }
    }
}

/** Receives PackageInstaller status callbacks (not exported; only our own PendingIntent targets it). */
class UpdateInstallReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != UpdateInstaller.ACTION_INSTALL_STATUS) return
        when (val status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)) {
            PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                @Suppress("DEPRECATION")
                val confirm: Intent? = if (Build.VERSION.SDK_INT >= 33) {
                    intent.getParcelableExtra(Intent.EXTRA_INTENT, Intent::class.java)
                } else {
                    intent.getParcelableExtra(Intent.EXTRA_INTENT)
                }
                if (confirm != null) {
                    confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    try {
                        context.startActivity(confirm)
                        UpdateInstaller.emit(InstallEvent.AwaitingUserConfirmation)
                    } catch (e: Exception) {
                        UpdateInstaller.emit(InstallEvent.Failed("Couldn't open the Android installer. Try again."))
                    }
                } else {
                    UpdateInstaller.emit(InstallEvent.Failed("Couldn't open the Android installer. Try again."))
                }
            }
            PackageInstaller.STATUS_SUCCESS -> UpdateInstaller.emit(InstallEvent.Succeeded)
            PackageInstaller.STATUS_FAILURE_ABORTED -> UpdateInstaller.emit(InstallEvent.CancelledByUser)
            else -> {
                val detail = when (status) {
                    PackageInstaller.STATUS_FAILURE_CONFLICT, PackageInstaller.STATUS_FAILURE_INCOMPATIBLE ->
                        "Android refused the update (it conflicts with the installed app's signature or version)."
                    PackageInstaller.STATUS_FAILURE_STORAGE -> "Not enough storage to install the update."
                    PackageInstaller.STATUS_FAILURE_BLOCKED -> "Installation was blocked on this device."
                    PackageInstaller.STATUS_FAILURE_INVALID -> "The update file is invalid."
                    else -> "The update could not be installed."
                }
                Log.w("UpdateInstaller", "Install failed: status=$status")
                UpdateInstaller.emit(InstallEvent.Failed(detail))
            }
        }
    }
}
