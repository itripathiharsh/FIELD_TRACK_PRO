package com.fieldtrackpro.android

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import androidx.navigation.compose.rememberNavController
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.notifications.NotificationHelper
import com.fieldtrackpro.android.ui.navigation.NavGraph
import com.fieldtrackpro.android.ui.navigation.Screen
import com.fieldtrackpro.android.ui.theme.FieldTrackProTheme
import com.fieldtrackpro.android.ui.viewmodel.AuthViewModel
import com.fieldtrackpro.android.ui.viewmodel.CheckInViewModel
import com.fieldtrackpro.android.ui.viewmodel.CollectionViewModel
import com.fieldtrackpro.android.ui.viewmodel.FormFillViewModel
import com.fieldtrackpro.android.ui.viewmodel.GeofenceViewModel
import com.fieldtrackpro.android.ui.viewmodel.MediaViewModel
import com.fieldtrackpro.android.ui.viewmodel.NotificationViewModel
import com.fieldtrackpro.android.ui.viewmodel.RequirementViewModel
import com.fieldtrackpro.android.ui.viewmodel.SignatureViewModel
import com.fieldtrackpro.android.ui.viewmodel.VisitDetailsViewModel
import com.fieldtrackpro.android.ui.viewmodel.VisitSummaryViewModel
import com.fieldtrackpro.android.ui.viewmodel.VisitsViewModel
import com.fieldtrackpro.android.workers.NotificationSyncScheduler
import com.fieldtrackpro.android.workers.OfflineSyncScheduler

class MainActivity : ComponentActivity() {

    private val tokenManager by lazy { TokenManager(applicationContext) }
    private val offlineQueueManager by lazy { OfflineQueueManager(applicationContext) }

    private var pendingNotificationVisitId: String? = null

    private val requestNotificationPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { isGranted ->
            if (isGranted) {
                NotificationSyncScheduler.syncImmediately(applicationContext)
            }
        }

    private val authViewModel by viewModels<AuthViewModel> {
        viewModelFactory { initializer { AuthViewModel(tokenManager) } }
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
        viewModelFactory { initializer { CollectionViewModel(tokenManager) } }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Initialize Notification Channel
        NotificationHelper.createNotificationChannel(applicationContext)

        // Request POST_NOTIFICATIONS on Android 13+ (API 33+)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                requestNotificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        }

        // Schedule offline sync & notification sync
        OfflineSyncScheduler.scheduleSync(application)
        NotificationSyncScheduler.schedulePeriodicSync(applicationContext)
        NotificationSyncScheduler.syncImmediately(applicationContext)

        // Check for incoming intent with visitId from notification tap
        handleNotificationIntent(intent)

        setContent {
            FieldTrackProTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    val navController = rememberNavController()

                    LaunchedEffect(pendingNotificationVisitId) {
                        pendingNotificationVisitId?.let { visitId ->
                            if (tokenManager.isLoggedIn()) {
                                navController.navigate(Screen.VisitDetails.createRoute(visitId))
                            }
                            pendingNotificationVisitId = null
                        }
                    }

                    NavGraph(
                        navController = navController,
                        tokenManager = tokenManager,
                        offlineQueueManager = offlineQueueManager,
                        authViewModel = authViewModel,
                        visitsViewModel = visitsViewModel,
                        visitDetailsViewModel = visitDetailsViewModel,
                        checkInViewModel = checkInViewModel,
                        mediaViewModel = mediaViewModel,
                        requirementViewModel = requirementViewModel,
                        geofenceViewModel = geofenceViewModel,
                        notificationViewModel = notificationViewModel,
                        formFillViewModel = formFillViewModel,
                        signatureViewModel = signatureViewModel,
                        visitSummaryViewModel = visitSummaryViewModel,
                        collectionViewModel = collectionViewModel
                    )
                }
            }
        }
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
            pendingNotificationVisitId = visitId
        }
    }

}
