package com.fieldtrackpro.android

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.enableEdgeToEdge
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import androidx.navigation.compose.rememberNavController
import com.fieldtrackpro.android.data.local.AccountDataWiper
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.notifications.NotificationHelper
import com.fieldtrackpro.android.ui.components.NotificationPermissionPrompt
import com.fieldtrackpro.android.ui.navigation.NavGraph
import com.fieldtrackpro.android.ui.navigation.Screen
import com.fieldtrackpro.android.ui.theme.FieldTrackProTheme
import com.fieldtrackpro.android.ui.viewmodel.AuthState
import com.fieldtrackpro.android.ui.viewmodel.AuthViewModel
import com.fieldtrackpro.android.ui.viewmodel.CheckInViewModel
import com.fieldtrackpro.android.ui.viewmodel.CheckOutViewModel
import com.fieldtrackpro.android.ui.viewmodel.CollectionViewModel
import com.fieldtrackpro.android.ui.viewmodel.FormFillViewModel
import com.fieldtrackpro.android.ui.viewmodel.GeofenceViewModel
import com.fieldtrackpro.android.ui.viewmodel.MediaViewModel
import com.fieldtrackpro.android.ui.viewmodel.MonthlyPlanningViewModel
import com.fieldtrackpro.android.ui.viewmodel.NotificationViewModel
import com.fieldtrackpro.android.ui.viewmodel.RequirementViewModel
import com.fieldtrackpro.android.ui.viewmodel.SignatureViewModel
import com.fieldtrackpro.android.ui.viewmodel.VisitDetailsViewModel
import com.fieldtrackpro.android.ui.viewmodel.VisitSummaryViewModel
import com.fieldtrackpro.android.ui.viewmodel.VisitsViewModel
import com.fieldtrackpro.android.utils.SessionManager
import com.fieldtrackpro.android.workers.NotificationSyncScheduler
import com.fieldtrackpro.android.workers.OfflineSyncScheduler
import kotlinx.coroutines.flow.collectLatest

class MainActivity : ComponentActivity() {

    private val tokenManager by lazy { TokenManager.getInstance(applicationContext) }
    private val offlineQueueManager by lazy { OfflineQueueManager.getInstance(applicationContext) }

    private val authViewModel by viewModels<AuthViewModel> {
        viewModelFactory { initializer {
            AuthViewModel(
                tokenManager,
                onSessionEnded = {
                    // Logout / account deletion: stop background work scoped to the ended session.
                    OfflineSyncScheduler.cancelSync(applicationContext)
                    NotificationSyncScheduler.cancelAll(applicationContext)
                },
                // Account deletion succeeded on the server: erase every local trace of that user (off the main
                // thread: file deletes + commit()s + WorkManager).
                onAccountDeleted = { userId ->
                    val app = applicationContext
                    Thread { AccountDataWiper.forContext(app).wipe(userId) }.start()
                },
                // Forced password change done: sync (paused meanwhile) and notifications resume.
                onPasswordChanged = {
                    OfflineSyncScheduler.ensureScheduled(applicationContext)
                    OfflineSyncScheduler.scheduleSync(applicationContext)
                    NotificationSyncScheduler.schedulePeriodicSync(applicationContext)
                    NotificationSyncScheduler.syncImmediately(applicationContext)
                }
            )
        } }
    }
    private val visitsViewModel by viewModels<VisitsViewModel> {
        viewModelFactory { initializer { VisitsViewModel(tokenManager, offlineQueueManager) } }
    }
    private val visitDetailsViewModel by viewModels<VisitDetailsViewModel> {
        viewModelFactory { initializer { VisitDetailsViewModel(tokenManager, offlineQueueManager) } }
    }
    private val checkInViewModel by viewModels<CheckInViewModel> {
        viewModelFactory { initializer { CheckInViewModel(application, tokenManager, offlineQueueManager) } }
    }
    private val checkOutViewModel by viewModels<CheckOutViewModel> {
        viewModelFactory { initializer { CheckOutViewModel(application, tokenManager, offlineQueueManager) } }
    }
    private val mediaViewModel by viewModels<MediaViewModel> {
        viewModelFactory { initializer { MediaViewModel(application, tokenManager) } }
    }
    private val requirementViewModel by viewModels<RequirementViewModel> {
        viewModelFactory { initializer { RequirementViewModel(tokenManager) } }
    }
    private val geofenceViewModel by viewModels<GeofenceViewModel> {
        viewModelFactory { initializer { GeofenceViewModel(application) } }
    }
    private val notificationViewModel by viewModels<NotificationViewModel> {
        viewModelFactory { initializer { NotificationViewModel(tokenManager) } }
    }
    private val formFillViewModel by viewModels<FormFillViewModel> {
        viewModelFactory { initializer { FormFillViewModel(tokenManager) } }
    }
    private val signatureViewModel by viewModels<SignatureViewModel> {
        viewModelFactory { initializer { SignatureViewModel(application, tokenManager) } }
    }
    private val visitSummaryViewModel by viewModels<VisitSummaryViewModel> {
        viewModelFactory { initializer { VisitSummaryViewModel(tokenManager, offlineQueueManager) } }
    }
    private val collectionViewModel by viewModels<CollectionViewModel> {
        viewModelFactory { initializer { CollectionViewModel(tokenManager, offlineQueueManager = offlineQueueManager) } }
    }
    private val appUpdateViewModel by viewModels<com.fieldtrackpro.android.update.AppUpdateViewModel>()

    private val monthlyPlanningViewModel by viewModels<MonthlyPlanningViewModel> {
        viewModelFactory { initializer { MonthlyPlanningViewModel(tokenManager) } }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        // Edge-to-edge on every API level (Android 15 enforces it for targetSdk 35 anyway): transparent bars, and each
        // screen picks dark or light status-bar icons (see SystemBarIcons). Default: dark icons on the light app.
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.light(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.light(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT)
        )
        super.onCreate(savedInstanceState)
        // The launch window is navy (one seamless splash, see themes.xml); once Compose owns the window, use the light
        // app background so keyboard/resize gaps never flash navy.
        window.setBackgroundDrawable(android.graphics.drawable.ColorDrawable(0xFFF5F6F9.toInt()))

        // Initialize Notification Channel
        NotificationHelper.createNotificationChannel(applicationContext)

        // POST_NOTIFICATIONS is requested after login (with an in-app disclosure) from NotificationPermissionPrompt below.

        // Schedule offline sync & notification sync
        OfflineSyncScheduler.ensureScheduled(applicationContext)
        NotificationSyncScheduler.schedulePeriodicSync(applicationContext)
        NotificationSyncScheduler.syncImmediately(applicationContext)

        // Check for incoming intent with visitId from notification tap
        handleNotificationIntent(intent)

        // In-app updates: apply any cached mandatory update immediately, then check the release manifest.
        if (savedInstanceState == null) appUpdateViewModel.onAppStart()

        setContent {
            FieldTrackProTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    val navController = rememberNavController()

                    // After login: disclosure + notification permission (not on cold start), and
                    // (re)start background syncs that are cancelled on logout/session expiry.
                    val authState by authViewModel.authState.collectAsState()
                    val isSignedIn = authState is AuthState.Authenticated || tokenManager.isLoggedIn()
                    NotificationPermissionPrompt(enabled = isSignedIn) {
                        NotificationSyncScheduler.syncImmediately(applicationContext)
                    }
                    LaunchedEffect(authState) {
                        if (authState is AuthState.Authenticated && !tokenManager.isPasswordChangeRequired()) {
                            OfflineSyncScheduler.ensureScheduled(applicationContext)
                            OfflineSyncScheduler.scheduleSync(applicationContext)
                            NotificationSyncScheduler.schedulePeriodicSync(applicationContext)
                        }
                    }

                    // Global session expiration & logout guard (User A -> User B isolation).
                    // sessionExpiredEvent is a ONE-SHOT event (see SessionManager): once consumed here it is
                    // gone, so a recreated activity (rotation, dark mode) cannot re-deliver it and log the user
                    // out again; a genuinely pending (not yet consumed) event still reaches the next collector.
                    LaunchedEffect(Unit) {
                        SessionManager.sessionExpiredEvent.collectLatest {
                            SessionManager.setPendingDeepLink(null)
                            clearAllUserScopedState()
                            navController.navigate(Screen.Login.route) {
                                popUpTo(0) { inclusive = true }
                                launchSingleTop = true
                            }
                        }
                    }

                    // Backend answered 403 PASSWORD_CHANGE_REQUIRED on some call: show the forced "Set a new
                    // password" screen (one-shot event; the flag itself is persisted by the interceptor).
                    LaunchedEffect(Unit) {
                        SessionManager.passwordChangeRequiredEvent.collectLatest {
                            if (tokenManager.isLoggedIn()) {
                                navController.navigate(Screen.ChangePassword.route) {
                                    popUpTo(0) { inclusive = true }
                                    launchSingleTop = true
                                }
                            }
                        }
                    }

                    val updateState by appUpdateViewModel.state.collectAsState()
                    val openInstallPermission = {
                        runCatching { startActivity(appUpdateViewModel.installPermissionIntent()) }
                        Unit
                    }
                    if (updateState.isMandatory) {
                        // A mandatory update replaces the whole app until it is installed (no bypass).
                        com.fieldtrackpro.android.ui.screens.update.MandatoryUpdateScreen(
                            state = updateState,
                            onUpdateNow = appUpdateViewModel::updateNow,
                            onOpenInstallPermission = openInstallPermission,
                            onExitApp = { finish() }
                        )
                        return@Surface
                    }
                    com.fieldtrackpro.android.ui.screens.update.OptionalUpdateDialog(
                        state = updateState,
                        onUpdateNow = appUpdateViewModel::updateNow,
                        onLater = appUpdateViewModel::later,
                        onOpenInstallPermission = openInstallPermission
                    )

                    NavGraph(
                        navController = navController,
                        tokenManager = tokenManager,
                        offlineQueueManager = offlineQueueManager,
                        authViewModel = authViewModel,
                        visitsViewModel = visitsViewModel,
                        visitDetailsViewModel = visitDetailsViewModel,
                        checkInViewModel = checkInViewModel,
                        checkOutViewModel = checkOutViewModel,
                        mediaViewModel = mediaViewModel,
                        requirementViewModel = requirementViewModel,
                        geofenceViewModel = geofenceViewModel,
                        notificationViewModel = notificationViewModel,
                        formFillViewModel = formFillViewModel,
                        signatureViewModel = signatureViewModel,
                        visitSummaryViewModel = visitSummaryViewModel,
                        collectionViewModel = collectionViewModel,
                        monthlyPlanningViewModel = monthlyPlanningViewModel
                    )
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        appUpdateViewModel.onResume()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleNotificationIntent(intent)
    }

    private fun handleNotificationIntent(intent: Intent?) {
        val visitId = intent?.getStringExtra(NotificationHelper.EXTRA_VISIT_ID)
            ?: intent?.extras?.getString(NotificationHelper.EXTRA_VISIT_ID)
            ?: intent?.getStringExtra("visit_id")
            ?: intent?.extras?.getString("visit_id")

        if (!visitId.isNullOrBlank()) {
            SessionManager.setPendingDeepLink(visitId)
        }
    }

    private fun clearAllUserScopedState() {
        OfflineSyncScheduler.cancelSync(applicationContext)
        NotificationSyncScheduler.cancelAll(applicationContext)
        geofenceViewModel.stopMonitoring()
        visitsViewModel.clearState()
        visitDetailsViewModel.clearState()
        checkInViewModel.resetState()
        checkOutViewModel.resetState()
        mediaViewModel.resetState()
        requirementViewModel.reset()
        formFillViewModel.resetState()
        signatureViewModel.resetState()
        visitSummaryViewModel.resetState()
        collectionViewModel.resetState()
        monthlyPlanningViewModel.resetState()
        notificationViewModel.resetState()
        authViewModel.resetAuthState()
        tokenManager.clear()
    }
}
