package com.fieldtrackpro.android.update

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.io.File

/** What the update UI shows. [mandatory] decides between a dismissible dialog and a blocking screen. */
sealed class UpdateUiState {
    object Hidden : UpdateUiState()
    data class Available(val manifest: UpdateManifest, val mandatory: Boolean, val reason: String?) : UpdateUiState()
    data class Downloading(val manifest: UpdateManifest, val mandatory: Boolean, val downloaded: Long, val total: Long?) : UpdateUiState()
    data class Verifying(val manifest: UpdateManifest, val mandatory: Boolean) : UpdateUiState()
    data class NeedsInstallPermission(val manifest: UpdateManifest, val mandatory: Boolean) : UpdateUiState()
    data class Installing(val manifest: UpdateManifest, val mandatory: Boolean) : UpdateUiState()
    data class Failed(val manifest: UpdateManifest, val mandatory: Boolean, val message: String) : UpdateUiState()

    val isMandatory: Boolean
        get() = when (this) {
            Hidden -> false
            is Available -> mandatory
            is Downloading -> mandatory
            is Verifying -> mandatory
            is NeedsInstallPermission -> mandatory
            is Installing -> mandatory
            is Failed -> mandatory
        }
}

/**
 * Platform-free update state machine (unit tested). [AppUpdateViewModel] supplies the Android pieces.
 */
class AppUpdateController(
    private val scope: CoroutineScope,
    private val installedVersionCode: () -> Long,
    private val expectedPackage: String,
    private val manifestUrl: String,
    private val allowedHosts: Set<String>,
    private val store: UpdateStore,
    private val now: () -> Long,
    private val fetchManifest: suspend (String) -> String,
    private val downloadApk: suspend (UpdateManifest, (Long, Long?) -> Unit) -> File,
    private val verifyApk: (File, UpdateManifest) -> ApkVerifier.Result,
    private val canInstall: () -> Boolean,
    private val install: suspend (File) -> Unit
) {
    private val _state = MutableStateFlow<UpdateUiState>(UpdateUiState.Hidden)
    val state: StateFlow<UpdateUiState> = _state.asStateFlow()

    private var checkJob: Job? = null
    private var workJob: Job? = null
    private var verifiedFile: File? = null

    private val enabled: Boolean get() = manifestUrl.isNotBlank()

    private fun busy(): Boolean = when (_state.value) {
        is UpdateUiState.Downloading, is UpdateUiState.Verifying, is UpdateUiState.Installing -> true
        else -> false
    }

    /** Cold start: apply the cached manifest at once (a mandatory update survives restarts offline), then check. */
    fun onAppStart() {
        if (!enabled) return
        store.lastManifestJson()?.let { apply(UpdateManifest.parse(it)) }
        check(coldStart = true)
    }

    /** Back in the foreground: re-check at most once an hour; resume an install waiting on the permission screen. */
    fun onResume() {
        if (!enabled) return
        val s = _state.value
        if (s is UpdateUiState.NeedsInstallPermission && canInstall()) {
            verifiedFile?.let { startInstall(s.manifest, s.mandatory, it) } ?: updateNow()
            return
        }
        check(coldStart = false)
    }

    fun check(coldStart: Boolean) {
        if (!enabled || busy() || checkJob?.isActive == true) return
        if (!UpdatePolicy.shouldCheckNow(store.lastCheckMs(), now(), coldStart)) return
        checkJob = scope.launch {
            try {
                val json = fetchManifest(manifestUrl)
                store.saveLastCheckMs(now())
                val manifest = UpdateManifest.parse(json)
                // An unreadable or tampered manifest is ignored entirely: it neither replaces the cached one nor
                // changes what is on screen.
                if (manifest != null && manifest.problem(expectedPackage, allowedHosts) == null) {
                    store.saveManifestJson(json)
                    if (!busy()) apply(manifest)
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                // Offline or host down: keep whatever the cached manifest decided. Never block on a failed check.
            }
        }
    }

    private fun apply(manifest: UpdateManifest?) {
        val decision = UpdatePolicy.decide(installedVersionCode(), manifest, expectedPackage, allowedHosts, store.snooze(), now())
        _state.value = when (decision) {
            is UpdatePolicy.Decision.Mandatory -> UpdateUiState.Available(decision.manifest, true, decision.reason)
            is UpdatePolicy.Decision.Optional -> UpdateUiState.Available(decision.manifest, false, null)
            else -> {
                // A mandatory gate is only lifted by a decision that is not mandatory (e.g. the update got installed).
                UpdateUiState.Hidden
            }
        }
    }

    /** "Later" on an optional update. Ignored for mandatory updates. */
    fun later() {
        val s = _state.value
        if (s.isMandatory || busy()) return
        val manifest = when (s) {
            is UpdateUiState.Available -> s.manifest
            is UpdateUiState.Failed -> s.manifest
            is UpdateUiState.NeedsInstallPermission -> s.manifest
            else -> return
        }
        store.saveSnooze(UpdatePolicy.snoozeAfterLater(store.snooze(), manifest.versionCode, now()))
        _state.value = UpdateUiState.Hidden
    }

    fun updateNow() {
        if (workJob?.isActive == true) return
        val s = _state.value
        val (manifest, mandatory) = when (s) {
            is UpdateUiState.Available -> s.manifest to s.mandatory
            is UpdateUiState.Failed -> s.manifest to s.mandatory
            is UpdateUiState.NeedsInstallPermission -> s.manifest to s.mandatory
            else -> return
        }
        workJob = scope.launch {
            try {
                _state.value = UpdateUiState.Downloading(manifest, mandatory, 0, manifest.apkSizeBytes)
                val file = downloadApk(manifest) { done, total ->
                    _state.value = UpdateUiState.Downloading(manifest, mandatory, done, total)
                }
                _state.value = UpdateUiState.Verifying(manifest, mandatory)
                when (val v = verifyApk(file, manifest)) {
                    is ApkVerifier.Result.Rejected -> {
                        file.delete()
                        _state.value = UpdateUiState.Failed(manifest, mandatory, v.message)
                        return@launch
                    }
                    ApkVerifier.Result.Ok -> Unit
                }
                verifiedFile = file
                if (!canInstall()) {
                    _state.value = UpdateUiState.NeedsInstallPermission(manifest, mandatory)
                } else {
                    startInstall(manifest, mandatory, file)
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: UpdateNetwork.VerificationException) {
                _state.value = UpdateUiState.Failed(manifest, mandatory, e.message ?: "The download failed verification.")
            } catch (e: UpdateNetwork.UntrustedHostException) {
                _state.value = UpdateUiState.Failed(manifest, mandatory, "The download address is not trusted, so the update was stopped.")
            } catch (e: Exception) {
                _state.value = UpdateUiState.Failed(
                    manifest, mandatory,
                    "Download interrupted. Check your internet connection and tap Retry; it continues where it stopped."
                )
            }
        }
    }

    private fun startInstall(manifest: UpdateManifest, mandatory: Boolean, file: File) {
        _state.value = UpdateUiState.Installing(manifest, mandatory)
        scope.launch {
            try {
                install(file)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                _state.value = UpdateUiState.Failed(manifest, mandatory, "Couldn't start the Android installer. Tap Retry.")
            }
        }
    }

    /** PackageInstaller callbacks. */
    fun onInstallEvent(event: InstallEvent) {
        val s = _state.value as? UpdateUiState.Installing ?: return
        when (event) {
            InstallEvent.AwaitingUserConfirmation -> Unit
            InstallEvent.Succeeded -> _state.value = UpdateUiState.Hidden // Android replaces and restarts the app
            InstallEvent.CancelledByUser -> _state.value = UpdateUiState.Available(
                s.manifest, s.mandatory,
                if (s.mandatory) "Installation was cancelled. This update is required to continue." else null
            )
            is InstallEvent.Failed -> _state.value = UpdateUiState.Failed(s.manifest, s.mandatory, event.message)
        }
    }
}
