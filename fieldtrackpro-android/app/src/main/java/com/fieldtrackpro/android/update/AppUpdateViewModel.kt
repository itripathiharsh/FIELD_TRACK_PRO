package com.fieldtrackpro.android.update

import android.app.Application
import android.content.Context
import android.content.Intent
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.BuildConfig
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import java.io.File

/** Activity-scoped owner of the update flow; survives rotation so a download is not restarted. */
class AppUpdateViewModel(application: Application) : AndroidViewModel(application) {

    private val app: Context = application
    private val allowedHosts: Set<String> = BuildConfig.UPDATE_ALLOWED_HOSTS
        .split(',').map { it.trim() }.filter { it.isNotEmpty() }.toSet()
    private val network = UpdateNetwork(allowedHosts)

    private val controller = AppUpdateController(
        scope = viewModelScope,
        installedVersionCode = { ApkVerifier.installedVersionCode(app).takeIf { it > 0 } ?: BuildConfig.VERSION_CODE.toLong() },
        expectedPackage = app.packageName,
        manifestUrl = BuildConfig.UPDATE_MANIFEST_URL,
        allowedHosts = allowedHosts,
        store = UpdateStore(app.getSharedPreferences(UpdateStore.PREFS_NAME, Context.MODE_PRIVATE)),
        now = { System.currentTimeMillis() },
        fetchManifest = { url -> network.fetchManifest(url) },
        downloadApk = { manifest, progress -> network.downloadApk(manifest, File(app.cacheDir, "updates"), progress) },
        verifyApk = { file, manifest -> ApkVerifier.verify(app, file, manifest.versionCode) },
        canInstall = { UpdateInstaller.canRequestInstalls(app) },
        install = { file -> UpdateInstaller.install(app, file) }
    )

    val state: StateFlow<UpdateUiState> = controller.state

    init {
        viewModelScope.launch { UpdateInstaller.events.collect { controller.onInstallEvent(it) } }
    }

    fun onAppStart() = controller.onAppStart()
    fun onResume() = controller.onResume()
    fun later() = controller.later()
    fun updateNow() = controller.updateNow()

    fun installPermissionIntent(): Intent = UpdateInstaller.installPermissionSettingsIntent(app)
}
